from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, cast

from langgraph.types import Command
from sqlalchemy import or_, select

from app.acp.client import RuntimePolicyError
from app.acp.pool import ACPProcessPool
from app.core.config import Settings
from app.core.deps import fail, require_project
from app.core.events import EventBus
from app.db.models import Project, Ticket, User, Workflow, WorkflowVersion
from app.engine.compiler import compile_workflow
from app.engine.context import RunContext
from app.engine.prompts import user_identity
from app.schemas.workflow import Graph
from app.services.agent_service import runtime_config
from app.services.git_service import GitService, safe_release_path
from app.services.notification_service import resolve_gate
from app.services.project_service import effective_agents


class TicketRunner:
    """Single-worker executor. Locks cover every workflow sharing a canonical workspace.

    Keep the workspace while waiting for confirmation or after a writing agent has run.
    Release it only for an input gate reached before any agent with write permission.
    """

    def __init__(
        self, sessions: Any, pool: ACPProcessPool, events: EventBus, settings: Settings, checkpointer: Any
    ) -> None:
        self.sessions, self.pool, self.events, self.settings = sessions, pool, events, settings
        self.checkpointer = checkpointer
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.graphs: dict[tuple[str, int], Any] = {}
        self.contexts: dict[str, RunContext] = {}
        self.workspace_locks: dict[str, asyncio.Lock] = {}
        self.owners: dict[str, str] = {}
        self.owned: dict[str, str] = {}
        self.action_locks: dict[str, asyncio.Lock] = {}
        self.closed = False
        self.adhoc_tasks: dict[str, asyncio.Task[None]] = {}
        self.capacity = asyncio.Semaphore(settings.max_concurrent_tickets)

    async def load(self, tid: str) -> tuple[Any, RunContext, Ticket]:
        async with self.sessions() as db:
            ticket = await db.get(Ticket, tid)
            if ticket is None:
                fail(404, "Không tìm thấy ticket", "not_found")
            project = await db.get(Project, ticket.project_id)
            snapshot = await db.scalar(
                select(WorkflowVersion).where(
                    WorkflowVersion.workflow_id == ticket.workflow_id,
                    WorkflowVersion.version == ticket.workflow_version,
                )
            )
            if snapshot is None:
                fail(409, "Không tìm thấy snapshot workflow", "missing_snapshot")
            key = (ticket.workflow_id, ticket.workflow_version)
            if key not in self.graphs:
                agents = await effective_agents(db, ticket.project_id)
                configs = {a.id: runtime_config(a, self.settings) for a in agents if a.is_active}
                try:
                    self.graphs[key] = compile_workflow(
                        Graph.model_validate(snapshot.graph), configs, self.checkpointer
                    )
                except ValueError:
                    fail(409, "Snapshot workflow không còn hợp lệ với cấu hình agent", "invalid_snapshot")
            return self.graphs[key], self.context(ticket, project), ticket

    def context(self, ticket: Ticket, project: Project) -> RunContext:
        if ticket.id not in self.contexts:
            ctx = RunContext(
                ticket.id,
                project.id,
                self.sessions,
                self.pool,
                self.events,
                self.settings,
                GitService(Path(project.workspace_path)),
                project.git_remote,
                project.default_branch,
            )

            async def terminal(command: str, output: str) -> None:
                await ctx.emit(
                    "terminal_output",
                    output,
                    sender_type="AGENT",
                    sender_name="@devops",
                    metadata={"command": command},
                )

            ctx.git.emit = terminal
            self.contexts[ticket.id] = ctx
        return self.contexts[ticket.id]

    def config(self, tid: str, ctx: RunContext) -> dict[str, Any]:
        return {"configurable": {"thread_id": tid, "ctx": ctx}, "recursion_limit": 100}

    async def checkpoint_error(self, graph: Any, ctx: RunContext, reason: str) -> None:
        try:
            snapshot = await graph.aget_state(self.config(ctx.ticket_id, ctx))
            if snapshot.values:
                # Update from the last committed node; retain the failed node as the next task.
                await graph.aupdate_state(self.config(ctx.ticket_id, ctx), {"error": reason})
        except Exception:
            await ctx.emit("log", "Không thể cập nhật checkpoint lỗi; lỗi được lưu trong ticket.result.")

    async def authorize(self, tid: str, user: Any, *, confirm: bool = False) -> Ticket:
        async with self.sessions() as db:
            identity = user_identity(user)
            actor = await db.get(User, identity["id"])
            ticket = await db.get(Ticket, tid)
            if not actor:
                fail(401, "Yêu cầu đăng nhập", "unauthorized")
            if ticket is None:
                fail(404, "Không tìm thấy ticket", "not_found")
            await require_project(db, ticket.project_id, actor, write=confirm, report=not confirm)
            return cast(Ticket, ticket)

    async def recover(self) -> None:
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(Ticket)
                    .where(
                        or_(
                            Ticket.status.in_(["RUNNING", "WAITING_USER_INPUT", "WAITING_USER_CONFIRM"]),
                            Ticket.result["adhoc_writer"].as_boolean().is_(True),
                        )
                    )
                    .order_by(Ticket.created_at)
                )
            ).all()
        for ticket in rows:
            try:
                if ticket.status == "RUNNING" and ticket.current_node_id == "manual_release":
                    async with self.sessions() as db:
                        project = await db.get(Project, ticket.project_id)
                    ctx = self.context(ticket, project)
                    await ctx.status(
                        "FAILED",
                        "manual_release",
                        {
                            "error": "Server restart; bấm Commit toàn bộ & đóng ticket để tiếp tục.",
                            **(
                                {"pending_release": ticket.result["pending_release"]}
                                if ticket.result.get("pending_release")
                                else {}
                            ),
                        },
                    )
                    continue
                if ticket.result.get("adhoc_writer") and ticket.status in {"OPEN", "FAILED"}:
                    async with self.sessions() as db:
                        project = await db.get(Project, ticket.project_id)
                    ctx = self.context(ticket, project)
                    ctx.had_writer = True
                    key = os.path.normcase(str(ctx.git.workspace.resolve()))
                    if key in self.owners:
                        raise ValueError("Conflicting recovered workspace owners")
                    await self.acquire(ticket.id, ctx)
                    continue
                graph, ctx, _ = await self.load(ticket.id)
                checkpoint = await graph.aget_state(self.config(ticket.id, ctx))
                if ticket.status == "RUNNING":
                    await self.checkpoint_error(graph, ctx, "server restart")
                    await ctx.status(
                        "FAILED",
                        ticket.current_node_id,
                        {
                            "error": "server restart",
                            **(
                                {"pending_release": ticket.result["pending_release"]}
                                if ticket.result.get("pending_release")
                                else {}
                            ),
                        },
                    )
                    await ctx.emit("error", "server restart — dùng retry để tiếp tục checkpoint")
                elif ticket.status == "WAITING_USER_CONFIRM" or checkpoint.values.get("wrote_files"):
                    key = os.path.normcase(str(ctx.git.workspace.resolve()))
                    if key in self.owners:
                        raise ValueError("Conflicting recovered workspace owners")
                    await self.acquire(ticket.id, ctx)
            except Exception:
                # Invalid/missing snapshots must not prevent other tickets or the server from starting.
                async with self.sessions() as db:
                    row = await db.get(Ticket, ticket.id)
                    row.status, row.result = "FAILED", {"error": "server restart: checkpoint không khả dụng"}
                    await db.commit()

    async def acquire(self, tid: str, ctx: RunContext) -> None:
        if tid in self.owned:
            return
        path = os.path.normcase(str(ctx.git.workspace.resolve()))
        lock = self.workspace_locks.setdefault(path, asyncio.Lock())
        queued = lock.locked()
        owner = self.owners.get(path)
        # Register the acquisition before any DB/log I/O so later tickets cannot overtake it.
        waiter = asyncio.create_task(lock.acquire())
        try:
            if queued:
                async with self.sessions() as db:
                    ticket = await db.get(Ticket, owner) if owner else None
                    flow = await db.get(Workflow, ticket.workflow_id) if ticket else None
                    content = (
                        f"Đang chờ ticket #{ticket.number} (workflow {flow.name}) giải phóng workspace…"
                        if flow and ticket
                        else "Đang chờ workspace…"
                    )
                await ctx.emit("log", content)
            await waiter
        except BaseException:
            if waiter.done() and not waiter.cancelled() and waiter.exception() is None:
                lock.release()
            else:
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
            raise
        self.owned[tid], self.owners[path] = path, tid

    def release(self, tid: str) -> None:
        path = self.owned.pop(tid, None)
        if path:
            self.owners.pop(path, None)
            self.workspace_locks[path].release()

    def schedule(self, tid: str, graph: Any, ctx: RunContext, value: Any) -> None:
        if tid in self.adhoc_tasks:
            fail(409, "Agent đang trả lời ad-hoc; thử lại sau", "agent_busy")
        if self.closed:
            fail(503, "Runner đang dừng", "runner_closed")
        if tid in self.tasks and not self.tasks[tid].done():
            fail(409, "Ticket đang chạy hoặc đang xếp hàng", "ticket_busy")
        self.tasks[tid] = asyncio.create_task(self.execute(tid, graph, ctx, value))

    async def execute(self, tid: str, graph: Any, ctx: RunContext, value: Any) -> None:
        retain = False
        admitted = False
        try:
            if self.capacity.locked():
                await ctx.emit("log", "Đang chờ giới hạn ticket chạy đồng thời…")
            await self.capacity.acquire()
            admitted = True
            await self.acquire(tid, ctx)
            await ctx.git.exclude_attachments()
            await ctx.status("RUNNING")
            await graph.ainvoke(value, self.config(tid, ctx))
            snapshot = await graph.aget_state(self.config(tid, ctx))
            interrupts = [i for task in snapshot.tasks for i in task.interrupts]
            if interrupts:
                payload = interrupts[0].value
                kind = payload["kind"]
                await ctx.status(
                    "WAITING_USER_CONFIRM" if kind == "human_confirm" else "WAITING_USER_INPUT",
                    payload["node_id"],
                )
                retain = kind == "human_confirm" or bool(snapshot.values.get("wrote_files")) or ctx.had_writer
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Never persist runtime exception details, which can contain provider credentials.
            reason = (
                "Native adapter bị khóa: chưa xác minh công cụ chỉ chạy qua permission guard. "
                "Cần client-only routing hoặc sandbox đã kiểm chứng."
                if isinstance(error, RuntimePolicyError)
                else f"Workflow thất bại ({type(error).__name__}); xem log runtime/Git đã lọc"
            )
            await ctx.emit("error", reason)
            await self.checkpoint_error(graph, ctx, reason)
            await ctx.status("FAILED", ctx.node_id, result={"error": reason})
            async with self.sessions() as db:
                await resolve_gate(db, tid, "FAILED", events=self.events)
        finally:
            if admitted:
                self.capacity.release()
            if not retain:
                self.release(tid)
                await self.pool.close_ticket(tid)
            self.tasks.pop(tid, None)

    async def adhoc(self, tid: str, agent_id: str, text: str, user: Any) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user)
            if tid in self.tasks or tid in self.adhoc_tasks:
                fail(409, "Agent đang bận; gửi lại sau lượt hiện tại", "agent_busy")
            if ticket.status in {"COMPLETED", "CANCELLED"}:
                fail(409, "Ticket đã kết thúc", "invalid_ticket_status")
            async with self.sessions() as db:
                if agent_id not in {
                    a.id for a in await effective_agents(db, ticket.project_id) if a.is_active
                }:
                    fail(422, "Mention không thuộc effective agents", "invalid_mention")
                project = await db.get(Project, ticket.project_id)
            ctx = self.context(ticket, project)
            self.adhoc_tasks[tid] = asyncio.create_task(self.execute_adhoc(ticket, ctx, agent_id, text))

    async def execute_adhoc(self, ticket: Ticket, ctx: RunContext, aid: str, text: str) -> None:
        from uuid import uuid4

        from app.acp.security import scrub, scrub_data
        from app.engine.nodes import stream_turn

        run_id = str(uuid4())
        retained = ticket.id in self.owned
        admitted = False
        handle = aid
        try:
            cfg = await ctx.agent(aid)
            handle = cfg.handle
            await self.capacity.acquire()
            admitted = True
            await self.acquire(ticket.id, ctx)
            await ctx.git.exclude_attachments()
            if cfg.permission_profile.allow_write:
                ctx.had_writer = True
                retained = True
                async with self.sessions() as db:
                    current_ticket = await db.get(Ticket, ticket.id)
                    current_ticket.result = {**current_ticket.result, "adhoc_writer": True}
                    await db.commit()
            session = await self.pool.get_or_start(cfg, ctx.git.workspace, ticket.id)
            await ctx.emit(
                "agent_turn_start",
                sender_type="AGENT",
                sender_name=handle,
                node_id="adhoc",
                run_id=run_id,
                metadata={"adhoc": True, "model": cfg.model, "runtime": cfg.runtime},
            )
            history = await ctx.chat_inputs()
            prompt = (
                "Ad-hoc reply outside workflow. Do not commit/push/release.\n"
                f"Ticket #{ticket.number}: {ticket.title}\n{ticket.description}\n"
            )
            for message in history:
                prompt += f"\nUser: {message['text']}"
                for attachment in message.get("attachments", []):
                    prompt += f"\nAttachment: {attachment['path']} ({attachment['mime']})"
            prompt += "\nReply to: " + text
            content, files = await stream_turn(ctx, session, prompt, "adhoc", run_id)
            content = scrub(content, cfg)
            await ctx.emit(
                "agent_turn_end",
                content,
                sender_type="AGENT",
                sender_name=handle,
                node_id="adhoc",
                run_id=run_id,
                metadata={
                    **scrub_data(ctx.completion_metadata or {}, cfg),
                    "adhoc": True,
                    "modified_files": files,
                },
            )
        except asyncio.CancelledError:
            await ctx.emit(
                "agent_turn_end",
                "Đã dừng agent",
                sender_type="AGENT",
                sender_name=handle,
                node_id="adhoc",
                run_id=run_id,
                metadata={"stopped": True, "adhoc": True},
            )
            raise
        except Exception:
            await ctx.emit(
                "error",
                "Ad-hoc agent gặp lỗi; kiểm tra cấu hình runtime",
                sender_type="AGENT",
                sender_name=handle,
                node_id="adhoc",
                run_id=run_id,
            )
        finally:
            if admitted:
                self.capacity.release()
            if not retained:
                self.release(ticket.id)
            self.adhoc_tasks.pop(ticket.id, None)

    async def stop_agent(self, tid: str, user: Any) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            await self.authorize(tid, user)
            task = self.adhoc_tasks.get(tid) or self.tasks.get(tid)
            if task is None:
                fail(409, "Không có agent đang chạy", "agent_idle")
            for (ticket_id, _), session in list(self.pool.sessions.items()):
                if ticket_id == tid and session.busy:
                    await session.cancel()
            was_adhoc = tid in self.adhoc_tasks
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if not was_adhoc:
                async with self.sessions() as db:
                    ticket = await db.get(Ticket, tid)
                if ticket.status == "RUNNING":
                    ctx = self.contexts[tid]
                    reason = "Người dùng đã dừng agent; bấm Thử lại để chạy lại node"
                    await ctx.emit("error", reason)
                    await ctx.status("FAILED", ctx.node_id, {"error": reason})

    async def start(self, tid: str, user: Any) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user)
            if ticket.status != "OPEN":
                fail(409, "Chỉ start ticket OPEN", "invalid_ticket_status")
            graph, ctx, ticket = await self.load(tid)
            self.schedule(
                tid,
                graph,
                ctx,
                {
                    "ticket_id": tid,
                    "project_id": ticket.project_id,
                    "workspace_path": str(ctx.git.workspace),
                    "title": ticket.title,
                    "description": ticket.description,
                    "number": ticket.number,
                    "outputs": [],
                    "user_inputs": [],
                    "last_route": {},
                    "modified_files": [],
                    "iteration": {},
                    "cursors": {},
                    "gate_counts": {},
                    "release": None,
                    "approval": False,
                    "wrote_files": False,
                    "error": None,
                },
            )

    async def resume(self, tid: str, user: Any, value: dict[str, Any], expected: str) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user, confirm=expected == "WAITING_USER_CONFIRM")
            if ticket.status != expected:
                fail(409, "Ticket không chờ thao tác này", "invalid_ticket_status")
            # gate_waiting can reach the browser just before ainvoke finishes saving its interrupt.
            previous = self.tasks.get(tid)
            if previous:
                await asyncio.shield(previous)
            graph, ctx, _ = await self.load(tid)
            snapshot = await graph.aget_state(self.config(tid, ctx))
            if not any(task.interrupts for task in snapshot.tasks):
                fail(409, "Checkpoint không có gate đang chờ", "missing_interrupt")
            value["user"] = user_identity(user)
            self.schedule(tid, graph, ctx, Command(resume=value))

    async def reply(self, tid: str, text: str, user: Any) -> None:
        if not text.strip():
            fail(422, "Câu trả lời không được rỗng", "empty_reply")
        await self.resume(tid, user, {"text": text}, "WAITING_USER_INPUT")

    async def confirm(self, tid: str, approved: bool, feedback: str | None, user: Any) -> None:
        await self.resume(
            tid, user, {"approved": approved, "feedback": feedback or ""}, "WAITING_USER_CONFIRM"
        )

    async def retry(self, tid: str, user: Any) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user)
            if ticket.status != "FAILED":
                fail(409, "Chỉ retry ticket FAILED", "invalid_ticket_status")
            graph, ctx, _ = await self.load(tid)
            snapshot = await graph.aget_state(self.config(tid, ctx))
            if not snapshot.values or not snapshot.next:
                fail(409, "Không có checkpoint để retry", "missing_checkpoint")
            await graph.aupdate_state(self.config(tid, ctx), {"error": None})
            self.schedule(tid, graph, ctx, None)

    async def force_release(self, tid: str, user: Any) -> None:
        """Explicit maintainer action; bypass the LLM review and human gates."""
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user, confirm=True)
            if ticket.status == "COMPLETED":
                return
            if self.closed:
                fail(503, "Runner đang dừng", "runner_closed")
            if ticket.result.get("force_release_running") and tid in self.tasks:
                return
            if ticket.status == "CANCELLED":
                fail(409, "Ticket đã bị huỷ", "invalid_ticket_status")
            for task in (self.adhoc_tasks.get(tid), self.tasks.get(tid)):
                if task:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            await self.pool.close_ticket(tid)
            async with self.sessions() as db:
                project = await db.get(Project, ticket.project_id)
            ctx = self.context(ticket, project)
            # Use current project settings even if an older run cached its context.
            workspace = await asyncio.to_thread(Path(project.workspace_path).resolve)
            if tid in self.owned and ctx.git.workspace != workspace:
                self.release(tid)
            ctx.git.workspace = workspace
            ctx.remote = project.git_remote
            ctx.run_id = None
            ctx.node_id = "manual_release"
            result = {**ticket.result, "force_release_running": True}
            await ctx.status("RUNNING", "manual_release", result)
            self.tasks[tid] = asyncio.create_task(
                self.execute_force_release(ticket, ctx, user_identity(user)["id"])
            )

    async def execute_force_release(self, ticket: Ticket, ctx: RunContext, actor_id: str) -> None:
        from app.services.audit import audit

        tid = ticket.id
        pending = ticket.result.get("pending_release")

        async def remember(result: dict[str, Any]) -> None:
            nonlocal pending
            pending = {**result, "remote": ctx.remote}
            await ctx.status(
                "RUNNING",
                "manual_release",
                {
                    "force_release_running": True,
                    "pending_release": pending,
                },
            )

        try:
            await self.acquire(tid, ctx)
            await ctx.emit(
                "log",
                "Đang commit toàn bộ code và push theo yêu cầu người dùng.",
                sender_type="AGENT",
                sender_name="@devops",
            )
            async with self.sessions() as db:
                await audit(db, "git.force_release_requested", tid, user_id=actor_id)
                await db.commit()
            await ctx.git.exclude_attachments()
            snapshot = await ctx.git.snapshot()
            files = [name for name in snapshot["files"] if safe_release_path(name)]
            if files:
                result = await ctx.git.commit_and_push(
                    files,
                    f"fix: ticket #{ticket.number} {ticket.title}",
                    remote=ctx.remote,
                    branch=snapshot["branch"],
                    on_commit=remember,
                )
            elif pending:
                if pending.get("remote") != ctx.remote:
                    raise ValueError("Remote changed since the pending release")
                result = await ctx.git.push_existing(pending, remote=ctx.remote)
            else:
                # A clean tree still needs a successful push before completion.
                full = (await ctx.git.run("rev-parse", "HEAD")).strip()
                result = {
                    "commit_hash": full[:7],
                    "commit_hash_full": full,
                    "branch": snapshot["branch"],
                    "files": [],
                    "message": "No source changes",
                    "insertions": 0,
                    "deletions": 0,
                }
                await remember(result)
                result = await ctx.git.push_existing(result, remote=ctx.remote)
            result = {**result, "forced_by": actor_id}
            async with self.sessions() as db:
                await audit(db, "git.force_release", tid, user_id=actor_id, payload=result)
                await resolve_gate(db, tid, "APPROVED", events=self.events)
                await db.commit()
            await ctx.status("COMPLETED", "manual_release", result)
            await ctx.emit(
                "log",
                f"Đã push commit {result['commit_hash']} và đóng ticket.",
                sender_type="AGENT",
                sender_name="@devops",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            reason = "Commit/push thất bại; ticket chưa đóng. Xem log Git và bấm lại để thử lại."
            await ctx.status(
                "FAILED",
                "manual_release",
                {
                    "error": reason,
                    **({"pending_release": pending} if pending else {}),
                },
            )
            await ctx.emit("error", reason)
        finally:
            self.release(tid)
            self.tasks.pop(tid, None)

    async def cancel(self, tid: str, user: Any) -> None:
        async with self.action_locks.setdefault(tid, asyncio.Lock()):
            ticket = await self.authorize(tid, user)
            if ticket.status in {"COMPLETED", "CANCELLED"}:
                fail(409, "Ticket đã kết thúc", "invalid_ticket_status")
            task = self.adhoc_tasks.get(tid) or self.tasks.get(tid)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await self.pool.close_ticket(tid)
            self.release(tid)
            async with self.sessions() as db:
                current_ticket = await db.get(Ticket, tid)
                current_ticket.result = {
                    k: v for k, v in current_ticket.result.items() if k != "adhoc_writer"
                }
                await db.commit()
            # Cancellation must work even when an agent was disabled/deleted or its snapshot
            # can no longer compile. It needs ticket/project identity, not a runnable graph.
            async with self.sessions() as db:
                project = await db.get(Project, ticket.project_id)
                ctx = self.context(ticket, project)
            async with self.sessions() as db:
                await resolve_gate(db, tid, "CANCELLED", events=self.events)
            await ctx.status("CANCELLED")

    async def state(self, tid: str) -> dict[str, Any]:
        # Inspect persisted state independently of current agent availability. Disabling
        # an agent must not make an old ticket's chat/state/WebSocket unreadable.
        async with self.sessions() as db:
            ticket = await db.get(Ticket, tid)
            if ticket is None:
                fail(404, "Không tìm thấy ticket", "not_found")
            version = await db.scalar(
                select(WorkflowVersion).where(
                    WorkflowVersion.workflow_id == ticket.workflow_id,
                    WorkflowVersion.version == ticket.workflow_version,
                )
            )
        stored = await self.checkpointer.aget_tuple({"configurable": {"thread_id": tid}})
        values = stored.checkpoint.get("channel_values", {}) if stored else {}
        statuses = {n["id"]: "idle" for n in version.graph.get("nodes", [])} if version else {}
        statuses.update(values.get("node_statuses", {}))
        for n in values.get("last_route", {}):
            statuses[n] = "done"
        for output in values.get("outputs", []):
            statuses[output["node_id"]] = "done"
        waiting = None
        for _, channel, interrupts in stored.pending_writes or [] if stored else []:
            if channel == "__interrupt__":
                for item in interrupts:
                    payload = item.value
                    waiting = {"kind": payload["kind"], "node_id": payload["node_id"], "payload": payload}
                    statuses[payload["node_id"]] = "waiting"
        if ticket.current_node_id:
            statuses[ticket.current_node_id] = (
                "running"
                if ticket.status == "RUNNING"
                else "failed"
                if ticket.status == "FAILED"
                else "waiting"
                if ticket.status.startswith("WAITING")
                else "done"
            )
        if ticket.status in {"CANCELLED", "COMPLETED", "FAILED"}:
            waiting = None
        return {
            "status": ticket.status,
            "last_seq": ticket.next_message_seq - 1,
            "result": ticket.result,
            "current_node_id": ticket.current_node_id,
            "waiting": waiting,
            "node_statuses": statuses,
        }

    async def close(self) -> None:
        self.closed = True
        for task in [*self.tasks.values(), *self.adhoc_tasks.values()]:
            task.cancel()
        await asyncio.gather(
            *list(self.tasks.values()), *list(self.adhoc_tasks.values()), return_exceptions=True
        )
        for tid in list(self.owned):
            self.release(tid)
        for tid in self.contexts:
            await self.pool.close_ticket(tid)
