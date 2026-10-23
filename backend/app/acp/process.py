"""Subprocess lifetime helpers, including descendants on Windows and POSIX."""

import asyncio
import contextlib
import os
import signal
import sys


async def stop_process(process: asyncio.subprocess.Process, grace: float = 5) -> None:
    if sys.platform == "win32":
        if process.returncode is None:
            # taskkill /T is required: terminating cmd.exe alone leaves npm/agent children alive.
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), grace)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            if sys.platform == "win32":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
    if sys.platform != "win32":
        # A parent can exit while a descendant ignores SIGTERM and retains pipe handles.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
