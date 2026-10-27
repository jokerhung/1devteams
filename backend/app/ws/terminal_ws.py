import asyncio
import logging
import time
from contextlib import suppress
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.deps import require_project
from app.core.security import token_subject
from app.db.models import User
from app.services.audit import terminal_audit
from app.ws.ticket_ws import authenticate

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/terminal/{project_id}")
async def terminal_socket(socket: WebSocket, project_id: UUID):
    await socket.accept()
    session = None
    receive = output = None
    try:
        settings = socket.app.state.settings
        if socket.headers.get("origin") and socket.headers["origin"] not in settings.origins:
            raise ValueError("Origin not allowed")
        if not settings.enable_remote_terminal:
            raise ValueError("Remote terminal đã bị tắt")
        # The same-origin WebSocket rewrite forwards the HttpOnly login cookie.
        # Cookie authentication requires an allowed browser Origin (CSWSH protection).
        cookie_token = socket.cookies.get("aiteams_session")
        if cookie_token and not socket.headers.get("authorization"):
            if socket.headers.get("origin") not in settings.origins:
                raise ValueError("Origin not allowed")
        user, token = await authenticate(socket, cookie_token)
        async with socket.app.state.db_session() as db:
            project = await require_project(db, str(project_id), user, write=True)
            workspace = await asyncio.to_thread(Path(project.workspace_path).resolve)
            if not any(workspace.is_relative_to(root) for root in settings.workspace_roots):
                raise ValueError("Workspace không được phép")
        manager = socket.app.state.pty_manager
        after_seq = max(0, int(socket.query_params.get("after_seq", "0")))
        session = await manager.attach(
            user.id,
            str(project_id),
            workspace,
            30,
            120,
            socket.query_params.get("session_id"),
            after_seq,
        )
        snapshot_seq = session.initial_seq
        await socket.send_json(
            {
                "type": "ready",
                "session_id": session.id,
                "reset": session.reset,
                "seq": snapshot_seq,
            }
        )
        for frame in session.initial_frames:
            await socket.send_json(frame)
        await socket.send_json({"type": "synced", "seq": snapshot_seq})
        checked_at = time.monotonic()
        last_ping = checked_at
        receive = asyncio.create_task(socket.receive_json())
        output = asyncio.create_task(session.queue.get())
        while True:
            done, _ = await asyncio.wait([receive, output], timeout=15, return_when=asyncio.FIRST_COMPLETED)
            if not token_subject(token, settings):
                raise ValueError("Phiên đăng nhập hết hạn")
            # Permission checks are periodic, not a DB round trip per keystroke/chunk.
            if time.monotonic() - checked_at >= 15:
                async with socket.app.state.db_session() as db:
                    actor = await db.get(User, user.id)
                    if actor is None:
                        raise ValueError("Tài khoản không còn tồn tại")
                    await require_project(db, str(project_id), actor, write=True)
                checked_at = time.monotonic()
            if not done or time.monotonic() - last_ping >= 15:
                await socket.send_json({"type": "ping"})
                last_ping = time.monotonic()
            if output in done:
                frame = output.result()
                if frame.get("seq", snapshot_seq + 1) > snapshot_seq:
                    await socket.send_json(frame)
                if frame["type"] in {"exit", "error"}:
                    break
                output = asyncio.create_task(session.queue.get())
            if receive in done:
                frame = receive.result()
                if not isinstance(frame, dict):
                    raise ValueError("Terminal frame không hợp lệ")
                if frame.get("type") == "input":
                    data = frame.get("data")
                    if not isinstance(data, str) or len(data) > 16384:
                        raise ValueError("Terminal input không hợp lệ")
                    if settings.terminal_audit_input:
                        await terminal_audit(manager.db, user.id, str(project_id), "input", data)
                    await asyncio.to_thread(session.process.write, data)
                elif frame.get("type") == "resize":
                    cols, rows = int(frame["cols"]), int(frame["rows"])
                    if not (10 <= cols <= 500 and 2 <= rows <= 200):
                        raise ValueError("Kích thước terminal không hợp lệ")
                    await asyncio.to_thread(session.process.setwinsize, rows, cols)
                receive = asyncio.create_task(socket.receive_json())
    except WebSocketDisconnect:
        pass
    except (ValueError, HTTPException, TimeoutError, KeyError, TypeError, OSError) as error:
        if isinstance(error, HTTPException):
            reason = (
                "Bạn cần quyền MAINTAINER để mở terminal"
                if error.status_code == 403
                else "Không xác thực được phiên terminal; hãy đăng nhập lại"
            )
        elif isinstance(error, ValueError):
            reason = str(error)
        else:
            reason = "Không thể mở phiên terminal; hãy kết nối lại"
        logger.warning("Terminal connection rejected: %s (%s)", reason, type(error).__name__)
        with suppress(WebSocketDisconnect, RuntimeError):
            await socket.send_json(
                {
                    "type": "error",
                    "data": reason,
                    "retryable": isinstance(error, (TimeoutError, OSError)),
                }
            )
            await socket.close(1008)
    finally:
        for task in [receive, output]:
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in [receive, output] if t), return_exceptions=True)
        if session:
            await socket.app.state.pty_manager.detach(session)
