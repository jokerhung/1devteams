from collections.abc import AsyncIterator
from typing import Annotated, NoReturn, TypeVar
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import token_subject
from app.db.models import Project, ProjectMember, User

bearer = HTTPBearer(auto_error=False)


def fail(status: int, detail: str, code: str = "invalid_request") -> NoReturn:
    raise HTTPException(status, detail={"detail": detail, "code": code})


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


DB = Annotated[AsyncSession, Depends(get_db)]


async def current_user(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    subject = token_subject(credentials.credentials, request.app.state.settings) if credentials else None
    try:
        user = await db.get(User, str(UUID(subject))) if subject else None
    except ValueError:
        user = None
    if user is None:
        fail(401, "Yêu cầu đăng nhập", "unauthorized")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def admin(user: CurrentUser) -> User:
    if user.system_role not in {"OWNER", "ADMIN"}:
        fail(403, "Chỉ quản trị viên được thực hiện thao tác này", "forbidden")
    return user


Admin = Annotated[User, Depends(admin)]


async def require_project(
    db: AsyncSession, project_id: str, user: User, write: bool = False, report: bool = False
) -> Project:
    project = await db.get(Project, project_id)
    if project is None:
        fail(404, "Không tìm thấy project", "not_found")
    if write:
        await db.execute(
            update(Project)
            .where(Project.id == project_id)
            .values(next_ticket_number=Project.next_ticket_number, updated_at=Project.updated_at)
        )
    if user.system_role in {"OWNER", "ADMIN"} or project.owner_id == user.id:
        return project
    role = await db.scalar(
        select(ProjectMember.project_role).where(
            ProjectMember.project_id == project_id,
            ProjectMember.member_type == "USER",
            ProjectMember.member_id == user.id,
        )
    )
    if role is None or (write and role != "MAINTAINER") or (report and role == "VIEWER"):
        fail(403, "Không có quyền trên project này", "forbidden")
    return project


EntityType = TypeVar("EntityType")


async def record(db: AsyncSession, model: type[EntityType], identifier: UUID | str) -> EntityType:
    result = await db.get(model, str(identifier))
    if result is None:
        fail(404, "Không tìm thấy dữ liệu", "not_found")
    return result
