"""Persist workspace access settings and apply them to all services immediately."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from app.core.config import Settings


class WorkspaceSettings:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.data_dir / "workspace-settings.json"
        self.lock = asyncio.Lock()

    def roots(self) -> list[str]:
        return [str(root) for root in self.settings.workspace_roots]

    @staticmethod
    def normalize(roots: list[str], *, check_exists: bool) -> list[str]:
        result: list[str] = []
        for raw in roots:
            raw = raw.strip()
            if not raw or any(char in raw for char in (";", "\n", "\r", "\0")):
                raise ValueError("Đường dẫn thư mục không hợp lệ.")
            folder = Path(raw)
            if not folder.is_absolute():
                raise ValueError(f"Cần đường dẫn tuyệt đối: {raw}")
            folder = folder.resolve()
            if check_exists and not folder.is_dir():
                raise ValueError(f"Thư mục không tồn tại hoặc không truy cập được: {raw}")
            if str(folder) not in result:
                result.append(str(folder))
        if not result:
            raise ValueError("Cần ít nhất một thư mục được phép truy cập.")
        return result

    async def load(self) -> None:
        def read():
            if not self.path.exists():
                return None
            value = json.loads(self.path.read_text(encoding="utf-8"))
            roots = value["roots"]
            if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
                raise ValueError("Invalid saved workspace settings")
            return self.normalize(roots, check_exists=False)

        roots = await asyncio.to_thread(read)
        if roots is not None:
            self.settings.allowed_workspace_roots = ";".join(roots)

    async def save(self, roots: list[str]) -> list[str]:
        async with self.lock:
            normalized = await asyncio.to_thread(self.normalize, roots, check_exists=True)

            def write():
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                    ) as file:
                        temporary = Path(file.name)
                        json.dump({"roots": normalized}, file, ensure_ascii=False, indent=2)
                        file.flush()
                        os.fsync(file.fileno())
                    os.replace(temporary, self.path)
                finally:
                    if temporary and temporary.exists():
                        temporary.unlink()

            # Complete disk persistence before applying the new access policy.
            task = asyncio.create_task(asyncio.to_thread(write))
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                self.settings.allowed_workspace_roots = ";".join(normalized)
                raise
            self.settings.allowed_workspace_roots = ";".join(normalized)
            return normalized
