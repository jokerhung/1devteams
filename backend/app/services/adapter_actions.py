"""Allowlisted adapter operations. Login output lives only in memory."""

import asyncio
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from app.acp.security import scrub_data
from app.core.config import REPO_ROOT, resolve_binary
from app.core.deps import fail

PACKAGES = {
    "claude-agent-acp": "@agentclientprotocol/claude-agent-acp",
    "codex-acp": "@agentclientprotocol/codex-acp",
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
}
PROVIDERS = {"claude-agent-acp": "claude", "codex-acp": "codex", "claude": "claude", "codex": "codex"}
Action = Literal["install", "login", "update"]


def command_for(adapter: str, action: Action) -> list[str]:
    if adapter not in PACKAGES:
        fail(404, "Adapter không hợp lệ")
    if action == "login":
        provider = PROVIDERS[adapter]
        binary = resolve_binary(provider)
        if not binary:
            fail(409, f"Cài {provider} trước khi đăng nhập.")
        return [binary, "login", "--device-auth"] if provider == "codex" else [binary, "auth", "login"]
    if action == "update" and not resolve_binary(adapter):
        fail(409, "Adapter chưa cài. Hãy chọn Install.")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        fail(409, "Máy chủ chưa có npm. Cài Node.js trước.")
    target = PACKAGES[adapter] + "@latest"
    # Prefer repo-local installs so PATH cannot select a different global CLI.
    return [npm, "install", "--save-dev", "--save-exact", target]


@dataclass
class AdapterJob:
    id: str
    user_id: str
    adapter: str
    action: Action
    command: list[str]
    status: str = "running"
    output: str = ""
    exit_code: int | None = None
    process: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            key: getattr(self, key) for key in ("id", "adapter", "action", "status", "output", "exit_code")
        }


class AdapterActions:
    def __init__(self):
        self.jobs: dict[str, AdapterJob] = {}

    def start(self, adapter: str, action: Action, user_id: str) -> AdapterJob:
        if any(job.status == "running" for job in self.jobs.values()):
            fail(409, "Một thao tác adapter đang chạy. Hoàn tất hoặc dừng trước khi tiếp tục.")
        command = command_for(adapter, action)
        for key in list(self.jobs):
            if len(self.jobs) < 30:
                break
            if self.jobs[key].status != "running":
                del self.jobs[key]
        job = AdapterJob(str(uuid4()), user_id, adapter, action, command)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self.run(job))
        return job

    def get(self, job_id: str, user_id: str) -> AdapterJob:
        job = self.jobs.get(job_id)
        if job is None or job.user_id != user_id:
            fail(404, "Không tìm thấy thao tác adapter")
        return job

    async def stop_process(self, job: AdapterJob):
        proc = job.process
        if proc is None or proc.returncode is not None:
            return
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill.exe",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        elif proc.returncode is None:
            proc.kill()
        await proc.wait()

    async def run(self, job: AdapterJob):
        try:
            async with asyncio.timeout(900):
                job.process = await asyncio.create_subprocess_exec(
                    *job.command,
                    cwd=REPO_ROOT,
                    stdin=asyncio.subprocess.PIPE if job.action == "login" else asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                assert job.process.stdout
                while chunk := await job.process.stdout.read(4096):
                    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", chunk.decode("utf-8", "replace"))
                    job.output = (job.output + scrub_data(clean))[-32000:]
                job.exit_code = await job.process.wait()
                job.status = "completed" if job.exit_code == 0 else "failed"
        except asyncio.CancelledError:
            job.status = "cancelled"
            raise
        except TimeoutError:
            job.status = "failed"
            job.output += "\nThao tác hết thời gian chờ. Hãy thử lại."
        except Exception:
            job.status = "failed"
            job.output += "\nKhông chạy được CLI. Kiểm tra Node.js và cấu hình máy chủ."
        finally:
            await self.stop_process(job)

    async def cancel(self, job: AdapterJob):
        if job.task and not job.task.done():
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)

    async def close(self):
        for job in self.jobs.values():
            await self.cancel(job)
