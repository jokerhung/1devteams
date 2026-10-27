"""Direct conversations with configured AI agents, independent of tickets."""

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.core.deps import DB, CurrentUser, fail, record, require_project
from app.db.models import Agent
from app.services.agent_chat import ChatContext, respond
from app.services.agent_service import runtime_config

router = APIRouter(prefix="/agent-chat", tags=["Agent chat"])


class DirectChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=200000)

    @model_validator(mode="after")
    def user_length(self):
        if self.role == "user" and len(self.content) > 12000:
            raise ValueError("User message exceeds 12000 characters")
        return self


class ChatRequest(BaseModel):
    agent_id: UUID
    project_id: UUID | None = None
    messages: list[DirectChatMessage] = Field(min_length=1, max_length=40)


class ChatReply(BaseModel):
    message: str
    reports: list[dict[str, Any]] = Field(default_factory=list)


@router.post("", response_model=ChatReply)
async def chat(body: ChatRequest, request: Request, db: DB, user: CurrentUser):
    if body.messages[-1].role != "user":
        fail(422, "Tin nhắn cuối phải là yêu cầu của bạn.")
    agent = await record(db, Agent, body.agent_id)
    if not agent.is_active:
        fail(409, "Agent đã ngừng hoạt động. Hãy chọn agent khác.")
    try:
        cfg = runtime_config(agent, request.app.state.settings)
    except ValueError:
        fail(409, "Cấu hình agent chưa đầy đủ. Kiểm tra Agents & Teams.")
    workspace = None
    project_context = (
        "Đây là hội thoại độc lập, chưa gắn với ticket hay project. "
        "Workspace hiện tại là thư mục làm việc riêng của lượt chat, không phải source của project. "
    )
    if body.project_id is not None:
        project = await require_project(
            db, str(body.project_id), user, write=cfg.permission_profile.allow_write
        )
        workspace = await asyncio.to_thread(Path(project.workspace_path).resolve)
        if not workspace.is_dir() or not any(
            workspace.is_relative_to(root) for root in request.app.state.settings.workspace_roots
        ):
            fail(422, "Workspace của project không tồn tại hoặc ngoài thư mục cho phép.")
        project_context = (
            f"Project: {project.name}. Workspace: {workspace}. "
            "Đây là hội thoại trong ngữ cảnh project, không tạo ticket. "
            "Chỉ làm việc trong workspace này. Không commit/push/release trong chat. "
        )
    prompt = (
        f"Bạn đang chat trực tiếp với người dùng với tư cách {agent.display_name} ({agent.handle}). "
        "Giữ vai trò và hướng dẫn đã cấu hình của bạn. "
        + project_context
        + "Dùng công cụ được cấp quyền để thực hiện yêu cầu và báo kết quả thực tế. "
        "Tiếp tục hội thoại JSON sau, trả lời tin nhắn user cuối cùng:\n"
    ) + json.dumps([message.model_dump() for message in body.messages], ensure_ascii=False)
    if len(prompt) + len(cfg.system_prompt) > min(request.app.state.settings.api_max_context_chars, 150000):
        fail(422, "Hội thoại quá dài. Hãy bắt đầu cuộc trò chuyện mới.")
    db.expunge_all()
    await db.rollback()
    pool = request.app.state.acp_pool
    scope = f"agent-chat-{user.id}-{uuid4()}"
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
    streaming = "text/event-stream" in request.headers.get("accept", "")

    async def progress(action: dict[str, Any]) -> None:
        await queue.put({"type": "action", **action})

    async def run() -> ChatReply:
        with TemporaryDirectory(prefix="aiteams-chat-", ignore_cleanup_errors=True) as folder:
            workspace_lock = None
            try:
                async with asyncio.timeout(request.app.state.settings.browser_run_timeout_sec):
                    if workspace is not None:
                        lock = request.app.state.ticket_runner.workspace_locks.setdefault(
                            os.path.normcase(str(workspace)), asyncio.Lock()
                        )
                        if lock.locked():
                            fail(
                                409,
                                "Workspace đang được sử dụng. Hãy thử lại khi lượt chạy hiện tại hoàn tất.",
                            )
                        await lock.acquire()
                        workspace_lock = lock
                    if streaming:
                        await progress(
                            {"id": "connect", "title": "Đang kết nối với agent…", "status": "in_progress"}
                        )
                    session = await pool.get_or_start(cfg, workspace or Path(folder), scope)
                    if streaming:
                        await progress(
                            {"id": "connect", "title": "Đã kết nối với agent", "status": "completed"}
                        )
                    context = ChatContext(
                        request.app.state.settings,
                        request.app.state.db_session,
                        request.app.state.ticket_runner.browser_manager,
                        progress=progress if streaming else None,
                    )
                    message, reports = await respond(session, prompt, context)
                    if not message:
                        fail(502, "Agent chưa trả lời. Hãy thử lại.")
                    return ChatReply(message=message, reports=reports)
            except TimeoutError:
                fail(504, "Agent chưa trả lời kịp. Hãy thử lại hoặc chọn agent khác.")
            except HTTPException:
                raise
            except Exception:
                fail(502, "Không kết nối được agent. Kiểm tra runtime trong Agents & Teams.")
            finally:
                try:
                    await pool.close_ticket(scope)
                finally:
                    if workspace_lock is not None:
                        workspace_lock.release()

    if not streaming:
        return await run()

    async def produce() -> None:
        try:
            reply = await run()
            await queue.put({"type": "reply", **reply.model_dump()})
        except HTTPException as error:
            detail = error.detail
            await queue.put(
                {
                    "type": "error",
                    "message": detail.get("detail", "Agent gặp lỗi")
                    if isinstance(detail, dict)
                    else str(detail),
                }
            )
        except Exception:
            await queue.put({"type": "error", "message": "Kết nối với agent bị gián đoạn. Hãy thử lại."})

    async def events():
        task = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                if event["type"] in {"reply", "error"}:
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
