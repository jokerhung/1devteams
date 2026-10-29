import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from sqlalchemy import delete, select

from app.core.deps import fail
from app.db.models import Ticket
from app.services.assets import attachment_paths, remove_ticket_files


@asynccontextmanager
async def deleting_tickets(db, request, ticket_ids: list[str]):
    """Remove inactive tickets in the caller's transaction; clean files after commit."""
    runner = request.app.state.ticket_runner
    async with AsyncExitStack() as stack:
        for tid in sorted(ticket_ids):
            lock = runner.action_locks.setdefault(tid, asyncio.Lock())
            if lock.locked():
                fail(409, "Ticket đang xử lý thao tác khác; hãy thử lại", "tickets_in_use")
            await stack.enter_async_context(lock)
        if any(tid in runner.tasks or tid in runner.adhoc_tasks for tid in ticket_ids):
            fail(409, "Hãy dừng agent đang hoạt động trước khi xóa", "tickets_in_use")
        active = await db.scalar(
            select(Ticket.id)
            .where(
                Ticket.id.in_(ticket_ids),
                Ticket.status.in_(["RUNNING", "WAITING_USER_INPUT", "WAITING_USER_CONFIRM"]),
            )
            .limit(1)
        )
        if active:
            fail(409, "Hãy hủy ticket đang chạy hoặc chờ phản hồi trước khi xóa", "tickets_in_use")
        paths = await attachment_paths(db, ticket_ids)
        await db.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))
        yield
        await remove_ticket_files(request.app.state.settings, ticket_ids, paths)
        for tid in ticket_ids:
            await runner.checkpointer.adelete_thread(tid)
