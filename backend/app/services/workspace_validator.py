import asyncio
import os
import sys
from pathlib import Path

from app.acp.process import stop_process
from app.core.config import Settings
from app.schemas.project import WorkspaceOut


async def git(path: Path, *args: str) -> tuple[int, str]:
    options = {"creationflags": 512} if sys.platform == "win32" else {"start_new_session": True}
    process = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        str(path),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=os.environ | {"GIT_TERMINAL_PROMPT": "0"},
        **options,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 10)
        return process.returncode or 0, output.decode("utf-8", "replace").strip()
    except (TimeoutError, asyncio.CancelledError):
        await stop_process(process)
        raise


async def validate_workspace(raw: str, settings: Settings) -> WorkspaceOut:
    path = Path(raw)
    exists = await asyncio.to_thread(path.is_dir)
    path = await asyncio.to_thread(path.resolve)
    allowed = Path(raw).is_absolute() and any(path.is_relative_to(root) for root in settings.workspace_roots)
    exists = exists and Path(raw).is_absolute()
    result = WorkspaceOut(
        exists=exists,
        within_allowed_roots=allowed,
        is_git_repo=False,
        current_branch=None,
        remotes=[],
        dirty_files_count=0,
    )
    if not exists or not allowed:
        return result
    try:
        code, value = await git(path, "rev-parse", "--is-inside-work-tree")
        result.is_git_repo = code == 0 and value == "true"
        if result.is_git_repo:
            _, result.current_branch = await git(path, "branch", "--show-current")
            _, remote = await git(path, "remote", "-v")
            result.remotes = sorted({line.split()[0] for line in remote.splitlines() if line.split()})
            _, dirty = await git(path, "status", "--porcelain")
            result.dirty_files_count = len(dirty.splitlines())
    except (OSError, TimeoutError):
        result.is_git_repo = False
    return result
