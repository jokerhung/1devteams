import asyncio
import json
import subprocess
import time
from collections import defaultdict, deque

import pytest

from app.acp.guard import DynamicPermissionGuard
from app.acp.handlers import ClientRequestHandlers
from app.acp.jsonrpc import RPCError
from app.acp.types import ACPStreamEvent
from tests.api.conftest import client as api_client_fixture
from tests.api.conftest import workspace as workspace_fixture

client = api_client_fixture
workspace = workspace_fixture


class ScriptedSession:
    def __init__(self, cfg, workspace, factory):
        self.cfg, self.workspace, self.factory = cfg, workspace, factory
        self.config_version = cfg.config_version
        self.modified_files = set()
        self.turn_interrupted = self.busy = False
        self.last_used = time.monotonic()
        self.alive = False
        self.closed = asyncio.Event()

    async def start(self):
        self.alive = True

    async def prompt(self, text):
        self.busy = True
        self.factory.prompts[self.cfg.handle].append((text, self.config_version))
        try:
            if self.cfg.handle in self.factory.blocked:
                self.factory.entered.set()
                await self.closed.wait()
                if self.turn_interrupted:
                    yield ACPStreamEvent(
                        agent_handle=self.cfg.handle,
                        event_type="completed",
                        metadata={"turn_interrupted": True},
                    )
                    return
            sequence = self.factory.scripts[self.cfg.handle]
            value = (
                sequence.popleft()
                if sequence
                else {
                    "@ba": "STR ready\n@@ROUTE: ready",
                    "@tester": "Tests pass\n@@ROUTE: pass",
                    "@leader": "@@RELEASE\n"
                    + json.dumps(
                        {
                            "approve": True,
                            "files": ["app.txt"],
                            "commit_message": "fix: repair app",
                            "concerns": [],
                        }
                    )
                    + "\n@@END",
                }.get(self.cfg.handle, "Review done")
            )
            if value == "ERROR":
                raise RuntimeError("scripted failure")
            if self.cfg.permission_profile.allow_write:
                old_text = (
                    (self.workspace / "app.txt").read_text() if (self.workspace / "app.txt").exists() else ""
                )
                (self.workspace / "app.txt").write_text(
                    f"repair {len(self.factory.prompts[self.cfg.handle])}\n"
                )
                self.modified_files.add("app.txt")
                events = []

                async def emit(event):
                    events.append(event)

                handlers = ClientRequestHandlers(
                    DynamicPermissionGuard(self.cfg.permission_profile, self.workspace, self.cfg.handle), emit
                )
                try:
                    await handlers.handle(
                        "terminal/create", {"command": "git", "args": ["commit", "-am", "bad"]}
                    )
                except RPCError:
                    pass
                for event in events:
                    yield event
                yield ACPStreamEvent(
                    agent_handle=self.cfg.handle,
                    event_type="file_edit",
                    metadata={
                        "path": "app.txt",
                        "old_text": old_text,
                        "new_text": (self.workspace / "app.txt").read_text(),
                    },
                )
            # Split chunks to exercise aggregation and marker parsing.
            for offset in range(0, len(value), 13):
                yield ACPStreamEvent(
                    agent_handle=self.cfg.handle,
                    event_type="message_chunk",
                    content=value[offset : offset + 13],
                )
            yield ACPStreamEvent(
                agent_handle=self.cfg.handle,
                event_type="completed",
                metadata={"stop_reason": "end_turn", "modified_files": sorted(self.modified_files)},
            )
        finally:
            self.busy = False

    async def cancel(self):
        self.closed.set()

    async def close(self):
        self.alive = False
        self.closed.set()


class ScriptFactory:
    def __init__(self):
        self.scripts = defaultdict(deque)
        self.prompts = defaultdict(list)
        self.blocked = set()
        self.entered = asyncio.Event()
        self.sessions = []

    def __call__(self, cfg, workspace):
        session = ScriptedSession(cfg, workspace, self)
        self.sessions.append(session)
        return session


@pytest.fixture
async def engine_client(client, tmp_path):
    repo = client.workspace
    remote = tmp_path / "remote.git"

    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout

    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Engine test")
    (repo / "app.txt").write_text("original\n")
    git("add", "app.txt")
    git("commit", "-m", "chore: initial")
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main")
    client.git, client.remote = git, remote
    client.factory = ScriptFactory()
    client.app.state.acp_pool.factory = client.factory
    yield client


async def settled(client, tid, expected):
    runner = client.app.state.ticket_runner
    task = runner.tasks.get(tid)
    if task:
        await asyncio.wait_for(asyncio.shield(task), 15)
    response = await client.get(f"/api/tickets/{tid}/state")
    assert response.status_code == 200, response.text
    if response.json()["status"] != expected:
        messages = (await client.get(f"/api/tickets/{tid}/messages?limit=1000")).json()
        diagnostic = [
            (m["event_type"], m["content"], m["metadata"])
            for m in messages
            if m["event_type"] in {"error", "terminal_output"}
        ]
        raise AssertionError((response.json(), diagnostic[-10:]))
    return response.json()
