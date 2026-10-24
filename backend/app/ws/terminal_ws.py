import asyncio
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
        user, token = await authenticate(socket)
        async with socket.app.state.db_session() as db:
            project = await require_project(db, str(project_id), user, write=True)
            workspace = await asyncio.to_thread(Path(project.workspace_path).resolve)
            if not any(workspace.is_relative_to(root) for root in settings.workspace_roots):
                raise ValueError("Workspace không được phép")
        manager = socket.app.state.pty_manager
        session = await manager.attach(user.id, str(project_id), workspace, 30, 120)
        await socket.send_json({"type": "ready", "session_id": session.id})
        if session.initial_replay:
            await socket.send_json({"type": "output", "data": session.initial_replay})
        receive = asyncio.create_task(socket.receive_json())
        output = asyncio.create_task(session.queue.get())
        while True:
            done, _ = await asyncio.wait([receive, output], timeout=15, return_when=asyncio.FIRST_COMPLETED)
            if not token_subject(token, settings):
                raise ValueError("Phiên đăng nhập hết hạn")
            async with socket.app.state.db_session() as db:
                actor = await db.get(User, user.id)
                if actor is None:
                    raise ValueError("Tài khoản không còn tồn tại")
                await require_project(db, str(project_id), actor, write=True)
            if not done:
                await socket.send_json({"type": "ping"})
            if output in done:
                frame = output.result()
                await socket.send_json(frame)
                if frame["type"] in {"exit", "error"}:
                    break
                output = asyncio.create_task(session.queue.get())
            if receive in done:
                frame = receive.result()
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
    except (ValueError, HTTPException, TimeoutError, KeyError, TypeError, OSError):
        with suppress(WebSocketDisconnect, RuntimeError):
            await socket.send_json(
                {"type": "error", "data": "Terminal bị từ chối: kiểm tra quyền MAINTAINER và cấu hình"}
            )
            await socket.close(1008)
    finally:
        for task in [receive, output]:
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in [receive, output] if t), return_exceptions=True)
        if session:
            await socket.app.state.pty_manager.detach(session)
