from app.acp.security import scrub_data
from app.db.models import AuditLog, TerminalAudit


async def audit(db, action: str, target: str, *, user_id=None, payload=None, ip=None):
    db.add(AuditLog(user_id=user_id, action=action, target=target, payload=scrub_data(payload or {}), ip=ip))
    await db.flush()


async def terminal_audit(sessions, user_id: str, project_id: str, action: str, data: str = ""):
    async with sessions() as db:
        db.add(TerminalAudit(user_id=user_id, project_id=project_id, action=action, data=scrub_data(data)))
        await audit(db, "terminal." + action, project_id, user_id=user_id)
        await db.commit()
