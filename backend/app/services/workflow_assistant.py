"""Canvas assistant: propose validated graphs without mutating saved workflows."""

import asyncio
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.acp.types import PermissionProfile
from app.core.deps import fail
from app.db.models import Agent
from app.schemas.workflow import Graph
from app.services.agent_service import runtime_config
from app.services.workflow_validator import validate_graph


class AssistantMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class AssistantRequest(BaseModel):
    graph: Graph
    messages: list[AssistantMessage] = Field(min_length=1, max_length=20)


class AssistantResponse(BaseModel):
    message: str
    graph: Graph | None = None
    errors: list[str] = Field(default_factory=list)


def parse_proposal(text: str, agents: list[Agent]) -> AssistantResponse:
    match = re.search(r"@@WORKFLOW\s*\n(.*?)\n@@END", text, re.DOTALL)
    if not match:
        if "@@WORKFLOW" in text:
            return AssistantResponse(message="@workflow trả sơ đồ chưa đầy đủ. Hãy yêu cầu thử lại.")
        return AssistantResponse(message=text.strip() or "@workflow chưa trả lời. Hãy thử lại.")
    message = (text[: match.start()] + text[match.end() :]).strip()
    try:
        graph = Graph.model_validate_json(match.group(1).strip())
    except ValidationError:
        return AssistantResponse(
            message=message or "Sơ đồ đề xuất không hợp lệ.", errors=["Graph JSON sai định dạng"]
        )
    errors = validate_graph(graph, [agent for agent in agents if agent.handle != "@workflow"])
    return AssistantResponse(
        message=message or "Đã đề xuất cập nhật workflow.", graph=None if errors else graph, errors=errors
    )


async def chat(body: AssistantRequest, agents: list[Agent], db, request: Request) -> AssistantResponse:
    if body.messages[-1].role != "user":
        fail(422, "Tin nhắn cuối phải là yêu cầu của user")
    agent = await db.scalar(select(Agent).where(Agent.handle == "@workflow", Agent.is_active.is_(True)))
    if agent is None:
        fail(409, "Chưa có agent @workflow đang hoạt động. Kiểm tra Agents & Teams.")
    settings = request.app.state.settings
    try:
        cfg = runtime_config(agent, settings).model_copy(
            update={"permission_profile": PermissionProfile(allow_read=False)}
        )
    except ValueError:
        fail(409, "Cấu hình @workflow chưa đầy đủ. Chọn model/runtime trong Agents & Teams.")
    context = {
        "graph": body.graph.model_dump(),
        "agents": [
            {
                "id": a.id,
                "handle": a.handle,
                "role": a.role_key,
                "runtime": a.runtime,
                "permissions": a.permission_profile,
            }
            for a in agents
            if a.is_active and a.handle != "@workflow"
        ],
        "conversation": [message.model_dump() for message in body.messages],
    }
    prompt = (
        "Thiết kế workflow; không gọi tool. Nếu đổi sơ đồ, trả TOÀN BỘ Graph trong "
        "@@WORKFLOW\n{JSON}\n@@END. Nếu hỏi rõ yêu cầu, trả text. "
        "Node type: start, end, agent, condition, human_input, human_confirm, git_release. "
        "Graph có nodes [{id,type,position:{x,y},data}], edges và viewport {x,y,zoom}. "
        "Sắp vị trí node dễ đọc, không chồng lên nhau. "
        "agent data: agent_id, label, instructions, routing=none|ba|tester|review, requires_write. "
        "Node tài liệu dùng document_name (tên file .md). "
        "Edge: id, source, target, sourceHandle. routing none dùng handle null; "
        "ba cần ready/need_info; tester/review cần pass/fail; condition cần true/false; "
        "human_confirm cần approved/rejected. Git release dùng success (failed tùy chọn). "
        "Đúng 1 start, có end, mọi node đi được từ start và tới end; "
        "mọi đường tới git_release phải qua human_confirm approved. "
        "Giữ ID của node cũ khi sửa. Không dùng @workflow làm node thực thi.\n"
        + json.dumps(context, ensure_ascii=False)
    )
    if len(prompt) + len(cfg.system_prompt) > min(settings.api_max_context_chars, 150000):
        fail(422, "Sơ đồ/lịch sử quá dài. Rút gọn hội thoại trước khi gửi.")
    # Authorization can acquire a project write lock. Never hold SQLite's
    # transaction open while waiting for a model to respond.
    db.expunge_all()
    await db.rollback()
    pool = request.app.state.acp_pool
    scope = f"workflow-assistant-{uuid4()}"
    # The assistant only needs the supplied graph, never a project's source checkout.
    # Native CLI descendants can briefly retain a cwd handle on Windows after
    # shutdown; best-effort cleanup must not turn a model reply into HTTP 500.
    with TemporaryDirectory(prefix="aiteams-workflow-", ignore_cleanup_errors=True) as folder:
        try:
            async with asyncio.timeout(100):
                session = await pool.get_or_start(cfg, Path(folder), scope)
                chunks = []
                size = 0
                async for event in session.prompt(prompt):
                    if event.event_type == "error":
                        fail(
                            502,
                            "@workflow gặp lỗi runtime: "
                            + (event.content[:1500] or "Kiểm tra model và kết nối."),
                        )
                    if event.event_type == "message_chunk":
                        size += len(event.content)
                        if size > 200000:
                            fail(502, "Phản hồi @workflow quá lớn. Hãy chia nhỏ yêu cầu.")
                        chunks.append(event.content)
                return parse_proposal("".join(chunks), agents)
        except TimeoutError:
            fail(504, "@workflow chưa trả lời kịp. Hãy thử lại hoặc chọn model khác.")
        except HTTPException:
            raise
        except Exception:
            fail(502, "Không khởi chạy được @workflow. Kiểm tra runtime trong Agents & Teams.")
        finally:
            await pool.close_ticket(scope)
