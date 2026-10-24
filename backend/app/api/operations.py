import asyncio
import json
import shutil
import sys
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.deps import DB, Admin, CurrentUser, fail, require_project
from app.db.models import AuditLog, Ticket, TicketMessage
from app.services.audit import terminal_audit
from app.services.common import fields

router = APIRouter(tags=["Operations"])


class TerminalInput(BaseModel):
    type: str
    data: str = Field(default="", max_length=16384)
    cols: int = Field(default=120, ge=10, le=500)
    rows: int = Field(default=30, ge=2, le=200)


@router.get("/projects/{pid}/terminal")
async def terminal_config(pid: UUID, request: Request, db: DB, user: CurrentUser):
    await require_project(db, str(pid), user, write=True)
    return {"enabled": request.app.state.settings.enable_remote_terminal}


@router.post("/projects/{pid}/terminal/input")
async def terminal_input(pid: UUID, body: TerminalInput, request: Request, db: DB, user: CurrentUser):
    await require_project(db, str(pid), user, write=True)
    manager = request.app.state.pty_manager
    if not request.app.state.settings.enable_remote_terminal:
        fail(403, "Terminal đã tắt")
    session = manager.sessions.get((user.id, str(pid)))
    if not session or not session.attached:
        fail(409, "Terminal chưa kết nối")
    if body.type == "input":
        if manager.settings.terminal_audit_input:
            await terminal_audit(manager.db, user.id, str(pid), "input", body.data)
        await asyncio.to_thread(session.process.write, body.data)
    elif body.type == "resize":
        await asyncio.to_thread(session.process.setwinsize, body.rows, body.cols)
    else:
        fail(422, "Terminal action không hợp lệ")
    return {"ok": True}


@router.get("/audit")
async def audit_list(
    db: DB, user: Admin, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
):
    return [
        fields(row)
        for row in (
            await db.scalars(
                select(AuditLog).order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    ]


@router.get("/metrics")
async def metrics(db: DB, user: Admin):
    counts = dict((await db.execute(select(Ticket.status, func.count()).group_by(Ticket.status))).all())
    denies = await db.scalar(
        select(func.count())
        .select_from(TicketMessage)
        .where(
            TicketMessage.event_type == "permission",
            TicketMessage.event_metadata["allowed"].as_boolean().is_(False),
        )
    )
    turns = (
        await db.scalars(
            select(TicketMessage).where(TicketMessage.event_type.in_(["agent_turn_start", "agent_turn_end"]))
        )
    ).all()
    starts = {r.run_id: r.created_at for r in turns if r.event_type == "agent_turn_start"}
    durations: dict[str, list[float]] = {}
    for row in turns:
        if row.event_type == "agent_turn_end" and row.run_id in starts:
            durations.setdefault(row.node_id or "adhoc", []).append(
                (row.created_at - starts[row.run_id]).total_seconds()
            )
    return {
        "tickets": counts,
        "guard_denies": denies,
        "node_average_seconds": {k: sum(v) / len(v) for k, v in durations.items()},
    }


@router.get("/settings/adapters")
async def adapters(request: Request, user: Admin, check_updates: bool = False):
    from app.core.config import REPO_ROOT, resolve_binary

    versions = {}
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    global_root = None
    if npm:
        proc = await asyncio.create_subprocess_exec(
            npm, "root", "-g", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            output, _ = await asyncio.wait_for(proc.communicate(), 10)
            if proc.returncode == 0 and output.strip():
                global_root = Path(output.decode().strip())
        except TimeoutError:
            proc.kill()
            await proc.wait()

    for package, binary in [
        ("@agentclientprotocol/claude-agent-acp", "claude-agent-acp"),
        ("@agentclientprotocol/codex-acp", "codex-acp"),
        ("@anthropic-ai/claude-code", "claude"),
        ("@openai/codex", "codex"),
    ]:
        folder = REPO_ROOT / "node_modules" / package / "package.json"
        if not folder.is_file() and global_root:
            folder = global_root / package / "package.json"
        value = await asyncio.to_thread(folder.read_text, encoding="utf-8") if folder.is_file() else None
        versions[binary] = {
            "version": json.loads(value)["version"] if value else None,
            "installed": resolve_binary(binary) is not None,
        }
        if check_updates:
            npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
            if npm:
                proc = await asyncio.create_subprocess_exec(
                    npm,
                    "view",
                    package,
                    "version",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    output, _ = await asyncio.wait_for(proc.communicate(), 20)
                    versions[binary]["latest"] = (
                        output.decode().strip()[:100] if proc.returncode == 0 else None
                    )
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
    return versions
