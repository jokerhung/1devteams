from uuid import UUID

from fastapi import APIRouter

from app.core.deps import DB, CurrentUser, fail
from app.db.models import Agent, UserPreference
from app.schemas.common import PreferenceInput
from app.services.common import commit

router = APIRouter(prefix="/me/preferences", tags=["Preferences"])


@router.get("")
async def preferences(db: DB, user: CurrentUser) -> dict:
    from sqlalchemy import select

    rows = (await db.scalars(select(UserPreference).where(UserPreference.user_id == user.id))).all()
    return {row.key: row.value for row in rows}


@router.put("")
async def put_preference(body: PreferenceInput, db: DB, user: CurrentUser) -> dict:
    if body.key == "default_mention_agent_id" and body.value is not None:
        try:
            identifier = str(UUID(str(body.value)))
        except ValueError:
            fail(422, "Agent ID không hợp lệ", "validation_error")
        agent = await db.get(Agent, identifier)
        if agent is None or not agent.is_active:
            fail(422, "Agent không tồn tại hoặc đã vô hiệu hóa", "validation_error")
    row = await db.get(UserPreference, (user.id, body.key))
    if row is None:
        row = UserPreference(user_id=user.id, key=body.key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    await commit(db)
    return {"key": row.key, "value": row.value}
