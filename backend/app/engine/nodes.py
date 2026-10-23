from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from app.acp.client import ACPSession
from app.acp.guard import DynamicPermissionGuard
from app.acp.types import AgentRuntimeConfig, AgentSession
from app.db.base import now
from app.db.models import Ticket
from app.engine.conditions import evaluate
from app.engine.context import RunContext
from app.engine.markers import ROUTES, parse_release, parse_route, routing_instruction
from app.engine.prompts import build_node_prompt
from app.engine.state import WorkflowState
from app.schemas.workflow import Node
from app.services.git_service import safe_release_path
from app.services.notification_service import create_gate, resolve_gate


async def gate(
    state: WorkflowState, ctx: RunContext, nid: str, kind: str, payload: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int]]:
    counts = dict(state.get("gate_counts", {}))
    seq = counts.get(nid, 0) + 1
    key = f"{state['ticket_id']}:{nid}:{seq}"
    payload = {"kind": kind, "node_id": nid, **payload, "gate_key": key}
    if not await ctx.gate_emitted(key):
        async with ctx.sessions() as db:
            ticket = await db.get(Ticket, state["ticket_id"])
            ticket.current_node_id = nid
            await create_gate(
                db,
                ticket,
                kind="CONFIRM" if kind == "human_confirm" else "INPUT",
                node_id=nid,
                interrupt_seq=seq,
                title="Xác nhận bản sửa lỗi để @leader commit & push"
                if kind == "human_confirm"
                else "Agent cần bạn bổ sung thông tin",
                body=str(payload.get("question", payload.get("message", ""))),
                events=ctx.events,
            )
        await ctx.emit("gate_waiting", node_id=nid, metadata=payload)
        await ctx.status("WAITING_USER_CONFIRM" if kind == "human_confirm" else "WAITING_USER_INPUT", nid)
    answer = interrupt(payload)
    if not isinstance(answer, dict):
        raise ValueError("Invalid gate response")
    async with ctx.sessions() as db:
        await resolve_gate(
            db,
            state["ticket_id"],
            "APPROVED"
            if kind == "human_confirm" and answer.get("approved")
            else "REJECTED"
            if kind == "human_confirm"
            else "ANSWERED",
            events=ctx.events,
        )
    counts[nid] = seq
    return answer, counts


async def stream_turn(
    ctx: RunContext,
    session: AgentSession,
    prompt: str,
    nid: str,
    run_id: str,
    images: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str]]:
    buffers: dict[str, str] = {}
    full = ""
    files: set[str] = set()
    stream = (
        session.prompt(prompt, images=images)
        if images and isinstance(session, ACPSession)
        else session.prompt(prompt)
    )
    iterator = stream.__aiter__()
    pending = asyncio.ensure_future(anext(iterator))
    last_flush = time.monotonic()

    async def emit(kind: str, content: str = "", metadata: dict[str, Any] | None = None) -> None:
        await ctx.emit(
            kind,
            content,
            sender_type="AGENT",
            sender_name=session.cfg.handle,
            node_id=nid,
            run_id=run_id,
            metadata=metadata or {},
        )

    async def flush() -> None:
        nonlocal last_flush
        for kind, content in buffers.items():
            await emit(kind, content)
        buffers.clear()
        last_flush = time.monotonic()

    try:
        while True:
            done, _ = await asyncio.wait(
                [pending], timeout=max(0.001, 0.15 - (time.monotonic() - last_flush))
            )
            if not done:
                await flush()
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                break
            if event.event_type == "message_chunk":
                full += event.content
            if event.event_type in {"message_chunk", "thought_chunk"}:
                buffers[event.event_type] = buffers.get(event.event_type, "") + event.content
            else:
                await flush()
                if event.event_type == "error":
                    await emit("error", event.content, event.metadata)
                    raise RuntimeError("Agent runtime failed")
                if event.event_type == "completed":
                    if event.metadata.get("turn_interrupted") or session.turn_interrupted:
                        raise RuntimeError("Agent restarted during turn")
                    files.update(event.metadata.get("modified_files", []))
                    await emit("log", "✔ stopReason=" + str(event.metadata.get("stop_reason", "end_turn")))
                else:
                    await emit(event.event_type, event.content, event.metadata)
            pending = asyncio.ensure_future(anext(iterator))
        await flush()
        files.update(session.modified_files)
        if session.turn_interrupted:
            raise RuntimeError("Agent restarted during turn")
        return full, sorted(files)
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close:
            await close()


async def agent_turn(
    node: Node, state: WorkflowState, ctx: RunContext, extra: str = ""
) -> tuple[str, list[str], AgentRuntimeConfig, str, dict[str, Any]]:
    agent_id = str(node.data["agent_id"])
    for attempt in range(2):
        cfg = await ctx.agent(agent_id)
        ctx.had_writer = ctx.had_writer or cfg.permission_profile.allow_write
        if node.type == "git_release" and (
            cfg.runtime == "openai-api" or not cfg.permission_profile.can_git_release
        ):
            raise ValueError("Agent no longer has Git release permission")
        run_id = (ctx.run_id if node.type == "git_release" and attempt == 0 else None) or str(uuid4())
        ctx.run_id, ctx.node_id = run_id, node.id
        await ctx.status("RUNNING", node.id)
        await ctx.emit(
            "agent_turn_start",
            sender_type="AGENT",
            sender_name=cfg.handle,
            node_id=node.id,
            run_id=run_id,
            metadata={"model": cfg.model},
        )
        session: AgentSession | None = None
        try:
            previous = ctx.pool.sessions.get((ctx.ticket_id, cfg.agent_id))
            session = await ctx.pool.get_or_start(cfg, Path(state["workspace_path"]), ctx.ticket_id)
            fresh = previous is not session or cfg.agent_id not in state.get("cursors", {})
            if fresh:
                await ctx.emit(
                    "log",
                    f"→ session/new cwd={state['workspace_path']}",
                    sender_type="AGENT",
                    sender_name=cfg.handle,
                    node_id=node.id,
                    run_id=run_id,
                )
            # All user chat is incorporated by a persisted sequence cursor, including attachments.
            chat = await ctx.chat_inputs()
            cursor = state.get("cursors", {}).get(cfg.agent_id, {}) if not fresh else {}
            new_chat = [m for m in chat if m["seq"] > cursor.get("chat_seq", 0)]
            prompt = build_node_prompt(node, cfg, state, fresh)
            images: list[dict[str, Any]] = []
            for item in new_chat:
                prompt += f"\n## User message\n{item['text']}"
                for attachment in item.get("attachments", []):
                    prompt += (
                        f"\n## File đính kèm\n{attachment['path']} "
                        f"({attachment['filename']}, {attachment['mime']})"
                    )
                    if cfg.runtime == "openai-api":
                        prompt += " — chỉ có mô tả, không có công cụ đọc tệp."
                    elif (
                        isinstance(session, ACPSession)
                        and session.agent_capabilities.get("promptCapabilities", {}).get("image")
                        and attachment["mime"].startswith("image/")
                    ):
                        guard = DynamicPermissionGuard(cfg.permission_profile, Path(state["workspace_path"]))
                        if guard.check_read(attachment["path"]).allowed:
                            path = guard.resolve_path(attachment["path"])
                            data = await asyncio.to_thread(path.read_bytes)
                            images.append(
                                {
                                    "type": "image",
                                    "mimeType": attachment["mime"],
                                    "data": base64.b64encode(data).decode("ascii"),
                                }
                            )
            if cfg.runtime == "openai-api":
                if cfg.permission_profile.allow_read:
                    prompt += "\n## Git diff\n" + await ctx.git.diff(
                        state.get("modified_files", []), ctx.settings.api_context_diff_chars
                    )
                if cfg.permission_profile.allow_read and node.data.get("routing") in {"ba", "review"}:
                    guard = DynamicPermissionGuard(cfg.permission_profile, Path(state["workspace_path"]))
                    for name in node.data.get("context_files", [])[:5]:
                        if not isinstance(name, str) or not guard.check_read(name).allowed:
                            continue
                        path = guard.resolve_path(name)
                        if path.is_file():

                            def read_file(path: Path = path) -> str:
                                with path.open("rb") as stream:
                                    return stream.read(12001).decode("utf-8", "replace")

                            value = await asyncio.to_thread(read_file)
                            prompt += f"\n## Context {name}\n{value[:12000]}" + (
                                "\n[truncated]" if len(value) > 12000 else ""
                            )
                suffix = routing_instruction(str(node.data.get("routing", "none")))
                budget = (
                    ctx.settings.api_max_context_chars - len(cfg.system_prompt) - len(extra) - len(suffix)
                )
                if budget < 200:
                    raise ValueError("API context budget is too small")
                if len(prompt) > budget:
                    half = (budget - 40) // 2
                    prompt = prompt[:half] + "\n[truncated context]\n" + prompt[-half:]
                prompt += suffix
            await ctx.emit(
                "log",
                f"→ session/prompt ({cfg.runtime} · {cfg.model})",
                sender_type="AGENT",
                sender_name=cfg.handle,
                node_id=node.id,
                run_id=run_id,
            )
            text, files = await stream_turn(ctx, session, prompt + extra, node.id, run_id, images)
            relative_files = []
            guard = DynamicPermissionGuard(cfg.permission_profile, Path(state["workspace_path"]))
            for name in files:
                try:
                    relative_files.append(guard.resolve_path(name).relative_to(guard.workspace).as_posix())
                except ValueError:
                    continue
            files = sorted(set(relative_files))
            routing = str(node.data.get("routing", "none"))
            clean, route = parse_route(text, routing)
            if routing in ROUTES and route is None:
                correction, _ = await stream_turn(
                    ctx, session, "Chỉ trả lời đúng 1 dòng:" + routing_instruction(routing), node.id, run_id
                )
                _, route = parse_route(correction, routing)
                if route is None:
                    route = "need_info" if routing == "ba" else "fail"
                    await ctx.emit(
                        "error",
                        "Agent trả marker không hợp lệ; chọn nhánh an toàn",
                        node_id=node.id,
                        run_id=run_id,
                    )
            cursors = dict(state.get("cursors", {}))
            cursors[cfg.agent_id] = {
                "outputs": len(state.get("outputs", [])) + 1,
                "inputs": len(state.get("user_inputs", [])),
                "chat_seq": max((m["seq"] for m in chat), default=0),
            }
            await ctx.emit(
                "agent_turn_end",
                clean,
                sender_type="AGENT",
                sender_name=cfg.handle,
                node_id=node.id,
                run_id=run_id,
                metadata={"route": route, "modified_files": files},
            )
            return clean, files if cfg.runtime != "openai-api" else [], cfg, route or "default", cursors
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            # Pool restart can cancel the shared startup task without cancelling this node.
            if attempt:
                raise RuntimeError("Agent startup interrupted twice") from None
            await ctx.emit(
                "log", "↻ cấu hình thay đổi trong lúc tạo session, chạy lại", node_id=node.id, run_id=run_id
            )
            await ctx.pool.discard_session(ctx.ticket_id, agent_id)
        except (RuntimeError, TimeoutError, OSError, ValueError):
            if attempt:
                raise
            restarted = session is not None and session.turn_interrupted
            await ctx.emit(
                "log",
                "↻ lượt bị dừng do sửa cấu hình agent, chạy lại"
                if restarted
                else "↻ lỗi runtime; thử lại một lần với session mới",
                node_id=node.id,
                run_id=run_id,
            )
            await ctx.pool.discard_session(ctx.ticket_id, agent_id)
    raise RuntimeError("Unreachable")


def make_node(node: Node, agents: dict[str, AgentRuntimeConfig]) -> Callable[..., Awaitable[dict[str, Any]]]:
    async def execute(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        ctx = cast(RunContext, config["configurable"]["ctx"])
        nid = node.id
        if node.type == "start":
            await ctx.status("RUNNING", nid)
            return {}
        if node.type == "end":
            await ctx.status(
                "FAILED" if state.get("error") else "COMPLETED",
                nid,
                state.get("release") or {"error": state.get("error")},
            )
            await ctx.pool.close_ticket(ctx.ticket_id)
            return {}
        if node.type in {"human_input", "human_confirm"}:
            payload: dict[str, Any] = {
                "message": node.data.get("message", "Xác nhận bản sửa lỗi"),
                "modified_files": state.get("modified_files", []),
            }
            if node.type == "human_input":
                payload["question"] = (
                    state.get("outputs", [])[-1]["text"] if state.get("outputs") else "Cần thêm thông tin"
                )
                payload["prompt_hint"] = "Agent đang chờ bạn bổ sung thông tin..."
            answer, counts = await gate(state, ctx, nid, node.type, payload)
            approved = node.type == "human_confirm" and answer.get("approved") is True
            return {
                "gate_counts": counts,
                "approval": approved,
                "last_route": state.get("last_route", {}) | {nid: "approved" if approved else "rejected"},
                "user_inputs": [
                    {
                        "node_id": nid,
                        "kind": "answer"
                        if node.type == "human_input"
                        else "approve"
                        if approved
                        else "feedback",
                        "text": answer.get("text", answer.get("feedback", "")),
                        "user": answer["user"],
                    }
                ],
            }
        if node.type == "condition":
            route = "true" if evaluate(str(node.data["expression"]), dict(state)) else "false"
            return {"last_route": state.get("last_route", {}) | {nid: route}}
        if node.type == "git_release":
            cfg = await ctx.agent(str(node.data["agent_id"]))
            if (
                not state.get("approval")
                or not cfg.permission_profile.can_git_release
                or cfg.runtime == "openai-api"
            ):
                raise ValueError("Git release requires human approval and release permission")
            ctx.run_id = str(uuid4())
            await ctx.status("RUNNING", nid)
            snapshot = await ctx.git.snapshot()
            if not snapshot["files"]:
                await ctx.emit("log", "Không có thay đổi để commit", node_id=nid)
                return {
                    "last_route": state.get("last_route", {}) | {nid: "failed"},
                    "approval": False,
                    "error": "Không có thay đổi để commit",
                }
            text, _, _, _, cursors = await agent_turn(
                node,
                state,
                ctx,
                "\nReview bản sửa và đề xuất commit. Không chạy git add/commit/push.\n"
                + snapshot["diff"]
                + "\nFiles: "
                + str(snapshot["files"])
                + "\nTrả đúng khối @@RELEASE\n"
                '{"approve":true,"files":["path"],"commit_message":"fix: description","concerns":[]}\n@@END',
            )
            plan = parse_release(text)
            files = []
            for name in dict.fromkeys(plan.files):
                if name not in snapshot["files"]:
                    raise ValueError("Leader đề xuất file không có thay đổi")
                if not safe_release_path(name):
                    await ctx.emit(
                        "error", "Loại file nhạy cảm khỏi release", metadata={"file": name}, node_id=nid
                    )
                else:
                    files.append(name)
            if not plan.approve or not files:
                await ctx.emit("log", "\n".join(plan.concerns) or "Leader không duyệt release", node_id=nid)
                return {
                    "last_route": state.get("last_route", {}) | {nid: "failed"},
                    "approval": False,
                    "error": "Leader không duyệt release",
                }
            latest = await ctx.agent(str(node.data["agent_id"]))
            if latest.runtime == "openai-api" or not latest.permission_profile.can_git_release:
                raise ValueError("Release permission revoked during review")
            result = await ctx.git.commit_and_push(
                files,
                plan.commit_message,
                remote=ctx.remote,
                branch=snapshot["branch"],
                default_branch=ctx.default_branch,
            )
            await ctx.emit(
                "message_chunk",
                f"Đã push commit `{result['commit_hash']}` lên `{result['branch']}`",
                sender_type="AGENT",
                sender_name=cfg.handle,
                node_id=nid,
            )
            return {
                "release": result,
                "approval": False,
                "cursors": cursors,
                "last_route": state.get("last_route", {}) | {nid: "success"},
            }
        iterations = dict(state.get("iteration", {}))
        count = iterations.get(nid, 0) + 1
        counts = state.get("gate_counts", {})
        inputs: list[dict[str, Any]] = []
        iteration_limit = node.data.get("max_iterations") or ctx.settings.max_node_iterations
        if count > iteration_limit:
            answer, counts = await gate(
                state,
                ctx,
                nid,
                "human_input",
                {
                    "question": (
                        f"Luồng đã lặp quá {iteration_limit} lần ở {nid}. "
                        "Nhập hướng dẫn để tiếp tục hoặc huỷ ticket."
                    )
                },
            )
            inputs = [{"node_id": nid, "kind": "answer", "text": answer["text"], "user": answer["user"]}]
            state = {**state, "user_inputs": state.get("user_inputs", []) + inputs}
            count = 1
        iterations[nid] = count
        clean, files, cfg, route, cursors = await agent_turn(node, state, ctx)
        wrote = state.get("wrote_files", False) or ctx.had_writer
        return {
            "outputs": [
                {
                    "node_id": nid,
                    "agent_handle": cfg.handle,
                    "text": clean,
                    "route": None if route == "default" else route,
                    "modified_files": files,
                    "at": now().isoformat(),
                }
            ],
            "last_route": state.get("last_route", {}) | {nid: route},
            "modified_files": sorted(set(state.get("modified_files", [])) | set(files)),
            "iteration": iterations,
            "gate_counts": counts,
            "cursors": cursors,
            "wrote_files": wrote,
            "approval": False if cfg.permission_profile.allow_write else state.get("approval", False),
            "user_inputs": inputs,
        }

    async def tracked(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        ctx = cast(RunContext, config["configurable"]["ctx"])
        ctx.node_id, ctx.run_id = node.id, None
        result = await execute(state, config)
        result["node_statuses"] = state.get("node_statuses", {}) | {node.id: "done"}
        return result

    return tracked
