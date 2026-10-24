"""Bounded, read-only browsing of a project's workspace."""

from pathlib import Path, PureWindowsPath

from app.core.deps import fail

MAX_TEXT_BYTES = 1024 * 1024
MAX_ENTRIES = 1000


def visible_path(path: Path) -> bool:
    for part in path.parts:
        name = part.lower()
        if (
            name in {".git", ".ssh", ".aiteams"}
            or (name.startswith(".env") and name not in {".env.example", ".env.sample", ".env.template"})
            or name.startswith(("id_rsa", "id_ed25519"))
            or name.endswith((".pem", ".key", ".p12", ".pfx"))
        ):
            return False
    return True


def workspace_path(workspace: str, roots: list[Path], name: str) -> tuple[Path, Path]:
    root = Path(workspace).resolve()
    if not any(root.is_relative_to(allowed.resolve()) for allowed in roots):
        fail(403, "Workspace ngoài thư mục cho phép", "invalid_workspace")
    relative = Path(name.replace("\\", "/"))
    if relative.is_absolute() or PureWindowsPath(name).drive or ".." in relative.parts:
        fail(403, "Đường dẫn ngoài workspace", "invalid_path")
    target = (root / relative).resolve()
    if (
        not target.is_relative_to(root)
        or not visible_path(relative)
        or not visible_path(target.relative_to(root))
    ):
        fail(403, "Không được đọc đường dẫn này", "invalid_path")
    return root, target


def list_workspace_files(workspace: str, roots: list[Path], name: str) -> dict:
    root, folder = workspace_path(workspace, roots, name)
    if not folder.is_dir():
        fail(404, "Không tìm thấy thư mục", "not_found")
    entries: list[dict[str, str]] = []
    truncated = False
    for child in folder.iterdir():
        try:
            relative = child.relative_to(root)
            resolved = child.resolve()
            if (
                not resolved.is_relative_to(root)
                or not visible_path(relative)
                or not visible_path(resolved.relative_to(root))
                or not (child.is_dir() or child.is_file())
            ):
                continue
            if len(entries) == MAX_ENTRIES:
                truncated = True
                break
            entries.append(
                {
                    "name": child.name,
                    "path": relative.as_posix(),
                    "kind": "directory" if child.is_dir() else "file",
                }
            )
        except (OSError, ValueError):
            continue
    return {
        "path": "" if folder == root else folder.relative_to(root).as_posix(),
        "entries": sorted(entries, key=lambda item: (item["kind"] != "directory", item["name"].casefold())),
        "truncated": truncated,
    }


def read_workspace_file(workspace: str, roots: list[Path], name: str) -> dict:
    root, target = workspace_path(workspace, roots, name)
    if not target.is_file():
        fail(404, "Không tìm thấy file", "not_found")
    with target.open("rb") as stream:
        data = stream.read(MAX_TEXT_BYTES + 1)
    if len(data) > MAX_TEXT_BYTES:
        fail(413, "Chỉ xem được file text tối đa 1 MB", "file_too_large")
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    if encoding != "utf-16" and (b"\x00" in data or any(byte < 8 for byte in data)):
        fail(415, "File nhị phân không hỗ trợ xem dạng text", "binary_file")
    text = data.decode(encoding, errors="replace")
    return {"path": target.relative_to(root).as_posix(), "content": text, "size": len(data)}
