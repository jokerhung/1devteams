"""Deterministic release operations. LLMs never receive a commit/push tool."""

import asyncio
import os
import re
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.acp.guard import DynamicPermissionGuard
from app.acp.process import stop_process
from app.acp.types import PermissionProfile


def commit_web_url(remote_url: str, sha: str) -> str | None:
    if not re.fullmatch(r"[a-f0-9]{40,64}", sha):
        return None
    value = remote_url.strip()
    if value.startswith("git@") and ":" in value:
        host, path = value[4:].split(":", 1)
    else:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "ssh"} or parsed.query or parsed.fragment:
            return None
        host, path = parsed.hostname or "", parsed.path.lstrip("/")
    if host not in {"github.com", "gitlab.com"}:
        return None
    path = path.removesuffix(".git").strip("/")
    if len(path.split("/")) < 2 or not re.fullmatch(r"[\w.-]+(?:/[\w.-]+)+", path):
        return None
    suffix = "commit" if host == "github.com" else "-/commit"
    return f"https://{host}/{path}/{suffix}/{sha}"


def safe_release_path(name: str) -> bool:
    parts = name.replace("\\", "/").lower().split("/")
    return (
        bool(name)
        and not name.startswith(("-", "/", "\\"))
        and not any(
            p in {"..", ".git", "node_modules", "dist", ".aiteams"}
            or p.startswith((".env", "id_rsa"))
            or p.endswith((".log", ".pem", ".key"))
            for p in parts
        )
    )


class GitService:
    def __init__(
        self, workspace: Path, emit: Callable[[str, str], Awaitable[None]] | None = None, timeout: float = 120
    ) -> None:
        self.workspace = workspace.resolve()
        self.emit, self.timeout = emit, timeout

    async def run(self, *args: str) -> str:
        if not args or args[0] not in {
            "status",
            "diff",
            "log",
            "rev-parse",
            "branch",
            "add",
            "commit",
            "push",
            "remote",
            "stash",
        }:
            raise ValueError("Git operation not permitted")
        if args[0] == "stash" and (
            len(args) != 5
            or args[1:4] != ("push", "-u", "-m")
            or not re.fullmatch(r"aiteams-ticket-\d+", args[4])
        ):
            raise ValueError("Only ticket recovery stash is permitted")
        if args[0] == "remote" and (
            len(args) != 3
            or args[1] != "get-url"
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", args[2])
        ):
            raise ValueError("Only reading a named remote is permitted")
        if any(a in {"--force", "-f", "--hard"} for a in args):
            raise ValueError("Unsafe git option")
        if args[0] == "push" and (len(args) != 3 or any(a.startswith("-") for a in args[1:])):
            raise ValueError("Push requires a remote and explicit branch")
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
        if args[0] == "branch" and args != ("branch", "--show-current"):
            raise ValueError("Only reading the current branch is permitted")
        if args[0] == "rev-parse" and args[1:] not in {
            ("HEAD",),
            ("--abbrev-ref", "HEAD"),
            ("--git-path", "info/exclude"),
            ("--absolute-git-dir",),
        }:
            raise ValueError("Unsafe rev-parse arguments")
        if args[0] == "add" and (
            len(args) < 3 or args[1] != "--" or any(not safe_release_path(f) for f in args[2:])
        ):
            raise ValueError("Unsafe add arguments")
        if args[0] == "commit" and (
            len(args) < 6
            or args[1:3] != ("--only", "-m")
            or args[4] != "--"
            or any(not safe_release_path(f) for f in args[5:])
        ):
            raise ValueError("Unsafe commit arguments")
        if args[0] == "diff":
            args = ("diff", "--no-ext-diff", "--no-textconv", *args[1:])
        process = await asyncio.create_subprocess_exec(
            "git",
            "-c",
            "core.hooksPath=" + os.devnull,
            "-c",
            "core.fsmonitor=false",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "push.gpgsign=false",
            *args,
            cwd=self.workspace,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **({"creationflags": 512} if sys.platform == "win32" else {"start_new_session": True}),
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
        except BaseException:
            await stop_process(process)
            raise
        output = (stdout + stderr).decode("utf-8", "replace")
        output = re.sub(r"(https?://)[^/@\s]+@", r"\1[redacted]@", output)
        if self.emit and args[0] != "remote":
            # Porcelain -z is parsed below; PostgreSQL text columns cannot store NUL bytes.
            log_output = output.replace("\x00", "\n")
            command = "git " + " ".join(args)
            # Bound individual events while preserving the complete command log.
            for offset in range(0, max(1, len(log_output)), 100000):
                await self.emit(command, log_output[offset : offset + 100000])
        if process.returncode:
            raise RuntimeError(
                "Git command failed; xem terminal_output. Commit local được giữ; "
                "kiểm tra remote/auth, không tự pull/rebase."
            )
        return output

    async def exclude_attachments(self) -> None:
        path = (await self.run("rev-parse", "--git-path", "info/exclude")).strip()
        target = (self.workspace / path).resolve()
        raw_git_dir = Path((await self.run("rev-parse", "--absolute-git-dir")).strip())
        git_dir = await asyncio.to_thread(raw_git_dir.resolve)
        if not target.is_relative_to(git_dir):
            raise ValueError("Git exclude path escapes the repository metadata directory")

        def write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            old = target.read_text(encoding="utf-8") if target.exists() else ""
            if "/.aiteams/attachments/" not in old.splitlines():
                target.write_text(old + "\n/.aiteams/attachments/\n", encoding="utf-8")

        await asyncio.to_thread(write)

    async def snapshot(self) -> dict[str, Any]:
        status = await self.run("status", "--porcelain=v1", "-z", "--untracked-files=all")
        entries = status.split("\x00")
        files: list[str] = []
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if len(entry) < 4:
                continue
            files.append(entry[3:])
            if "R" in entry[:2] or "C" in entry[:2]:
                if index < len(entries):
                    files.append(entries[index])
                index += 1
        branch = (await self.run("branch", "--show-current")).strip()
        allowed = [f for f in dict.fromkeys(files) if safe_release_path(f)]
        diff = await self.diff(allowed, 60000)
        has_head = await self.has_head()
        return {
            "files": list(dict.fromkeys(files)),
            "diff": diff,
            "branch": branch,
            "stat": (
                await self.run("diff", "--stat", *(["HEAD"] if has_head else ["--cached"]), "--", *allowed)
            )[:10000]
            if allowed
            else "",
        }

    async def has_head(self) -> bool:
        try:
            await self.run("rev-parse", "HEAD")
            return True
        except RuntimeError:
            return False

    async def diff(self, files: list[str], limit: int = 40000) -> str:
        guard = DynamicPermissionGuard(PermissionProfile(), self.workspace)
        blocks: list[str] = []
        used = 0
        has_head = await self.has_head() if files else False
        for name in files:
            if not safe_release_path(name) or not guard.check_read(name).allowed:
                continue
            value = await self.run("diff", "HEAD", "--", name) if has_head else ""
            path = guard.resolve_path(name)
            if not value and path.is_file():

                def read_file(path: Path = path) -> str:
                    with path.open("rb") as stream:
                        return stream.read(12001).decode("utf-8", "replace")

                value = await asyncio.to_thread(read_file)
            block = f"\n### {name}\n{value[:12000]}" + ("\n[truncated]" if len(value) > 12000 else "")
            remaining = limit - used
            if len(block) > remaining:
                blocks.append(block[: max(0, remaining)] + "\n[truncated total diff]")
                break
            blocks.append(block)
            used += len(block)
        return "".join(blocks)

    async def commit_and_push(
        self, files: list[str], message: str, *, remote: str, branch: str, default_branch: str = ""
    ) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", remote):
            raise ValueError("Invalid remote name")
        actual = (await self.run("branch", "--show-current")).strip()
        if actual == "HEAD" or actual != branch or not branch or branch.startswith("-") or ":" in branch:
            raise ValueError("Detached HEAD hoặc branch đã thay đổi")
        snapshot = await self.snapshot()
        guard = DynamicPermissionGuard(PermissionProfile(), self.workspace)
        if not files or any(
            f not in snapshot["files"] or not safe_release_path(f) or not guard.check_read(f).allowed
            for f in files
        ):
            raise ValueError("Release contains unsafe or unchanged files")
        if default_branch and actual != default_branch and self.emit:
            await self.emit("warning", f"Đang push branch {actual}, khác default {default_branch}")
        message = message.strip().replace("\n", " ").replace("\r", " ")
        if not re.fullmatch(
            r"(feat|fix|refactor|perf|test|docs|chore|build|ci|style)(\([^\r\n]+\))?: .{3,}", message
        ):
            message = "fix: " + (message if len(message) >= 3 else "ticket update")
        await self.run("add", "--", *files)
        stats = await self.run("diff", "--numstat", "--cached", "--", *files)
        # --only excludes unrelated entries already in the user's index.
        await self.run("commit", "--only", "-m", message, "--", *files)
        full = (await self.run("rev-parse", "HEAD")).strip()
        insertions = deletions = 0
        for line in stats.splitlines():
            values = line.split("\t")
            if len(values) >= 2 and values[0].isdigit() and values[1].isdigit():
                insertions += int(values[0])
                deletions += int(values[1])
        if (await self.run("rev-parse", "--abbrev-ref", "HEAD")).strip() != branch:
            raise ValueError("Branch changed before push; local commit preserved")
        output = await self.run("push", remote, branch)
        commit_url = commit_web_url(await self.run("remote", "get-url", remote), full)
        return {
            **({"commit_url": commit_url} if commit_url else {}),
            "commit_hash": full[:7],
            "commit_hash_full": full,
            "branch": branch,
            "files": files,
            "message": message,
            "insertions": insertions,
            "deletions": deletions,
            "push_output": output,
        }
