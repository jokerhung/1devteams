"""Deterministic provider for browser tests only; production never imports this module."""
import asyncio
import json
import time

from app.acp.guard import DynamicPermissionGuard
from app.acp.handlers import ClientRequestHandlers
from app.acp.jsonrpc import RPCError
from app.acp.types import ACPStreamEvent


class FakeSession:
    def __init__(self, cfg, workspace):
        self.cfg, self.workspace = cfg, workspace
        self.config_version = cfg.config_version
        self.modified_files = set()
        self.turn_interrupted = self.busy = False
        self.last_used = time.monotonic()
        self.alive = False
        self.turns = 0

    async def start(self):
        self.alive = True

    async def prompt(self, text):
        self.busy = True
        self.turns += 1
        (self.workspace / ".aiteams").mkdir(exist_ok=True)
        # Allows the browser test to verify actual attachment paths reached the next prompt.
        with (self.workspace / ".aiteams" / "prompt-checks.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"agent": self.cfg.handle, "text": text}, ensure_ascii=False) + "\n")
        try:
            yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="thought_chunk", content="Đang kiểm tra yêu cầu và quyền truy cập.")
            await asyncio.sleep(0.2)
            if self.cfg.handle == "@ba":
                result = "Bạn vui lòng cung cấp trình duyệt và các bước tái tạo?\n@@ROUTE: need_info" if "Chrome" not in text else "STR: 1. Mở đối soát 2. Bấm Xuất Excel 3. File được tải xuống.\n@@ROUTE: ready"
            elif self.cfg.handle == "@developer":
                new = f"Excel export repaired, pass {self.turns}\n"
                events = []

                async def emit(event):
                    events.append(event)

                handlers = ClientRequestHandlers(DynamicPermissionGuard(self.cfg.permission_profile, self.workspace, self.cfg.handle), emit)
                yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="tool_call", metadata={"toolCallId": "edit", "title": "Edit app.txt", "status": "in_progress"})
                await handlers.handle("fs/write_text_file", {"path": str(self.workspace / "app.txt"), "content": new})
                try:
                    await handlers.handle("terminal/create", {"command": "git", "args": ["commit", "-am", "blocked"]})
                except RPCError:
                    pass
                for event in events:
                    yield event
                self.modified_files.add("app.txt")
                yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="tool_call_update", metadata={"toolCallId": "edit", "status": "completed"})
                result = "Đã sửa thao tác xuất Excel. Xin tester kiểm tra."
            elif self.cfg.handle == "@tester":
                yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="terminal_output", content="PASS export test\n1 passed", metadata={"command": "test export", "exit_code": 0})
                result = "PASS: xuất Excel thành công.\n@@ROUTE: pass"
            elif self.cfg.handle == "@leader":
                for line in ["Review diff", "Kiểm tra phạm vi file", "Sẵn sàng phát hành"]:
                    yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="log", content=line)
                    await asyncio.sleep(0.4)
                result = '@@RELEASE\n{"approve":true,"files":["app.txt"],"commit_message":"fix: repair Excel export","concerns":[]}\n@@END'
            else:
                result = "Đã xem yêu cầu."
            for offset in range(0, len(result), 24):
                yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="message_chunk", content=result[offset:offset + 24])
                await asyncio.sleep(0.04)
            yield ACPStreamEvent(agent_handle=self.cfg.handle, event_type="completed", metadata={"stop_reason": "end_turn", "model_effective": "browser-fixture-model", "modified_files": sorted(self.modified_files)})
        finally:
            self.busy = False

    async def cancel(self):
        self.turn_interrupted = True

    async def close(self):
        self.alive = False


def factory(cfg, workspace):
    return FakeSession(cfg, workspace)
