from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.core.deps import fail


def fields(entity) -> dict:
    return {column.key: getattr(entity, column.key) for column in inspect(entity).mapper.column_attrs}


async def commit(db) -> None:
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        fail(409, "Dữ liệu bị trùng hoặc đang được tham chiếu", "conflict")


def patch_values(body, nullable=()) -> dict:
    values = body.model_dump(exclude_unset=True)
    if any(value is None and key not in nullable for key, value in values.items()):
        fail(422, "Không được để trống trường bắt buộc", "validation_error")
    return values
