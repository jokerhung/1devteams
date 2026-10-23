from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import DB, Admin, CurrentUser, fail, record
from app.core.security import hash_password
from app.db.models import User
from app.schemas.user import UserCreate, UserOut, UserPatch
from app.services.common import commit, patch_values

router = APIRouter(prefix="/users", tags=["Users"])


def initials(name: str) -> str:
    return "".join(part[0] for part in name.split()[:4]).upper()


@router.get("", response_model=list[UserOut])
async def list_users(db: DB, user: Admin):
    return (await db.scalars(select(User).order_by(User.display_name))).all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(body: UserCreate, db: DB, user: Admin):
    if body.system_role == "OWNER" and user.system_role != "OWNER":
        fail(403, "Chỉ OWNER được tạo OWNER", "forbidden")
    try:
        hashed = await hash_password(body.password.get_secret_value())
    except ValueError:
        fail(422, "Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte", "validation_error")
    entity = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hashed,
        system_role=body.system_role,
        avatar_initials=initials(body.display_name),
    )
    db.add(entity)
    await commit(db)
    return entity


@router.patch("/{uid}", response_model=UserOut)
async def patch_user(uid: UUID, body: UserPatch, db: DB, user: CurrentUser):
    target = await record(db, User, uid)
    values = patch_values(body)
    elevated = user.system_role in {"OWNER", "ADMIN"}
    if user.id != target.id and not elevated:
        fail(403, "Không được sửa người dùng khác", "forbidden")
    if "system_role" in values and values["system_role"] != target.system_role:
        if not elevated or (
            user.system_role != "OWNER"
            and (target.system_role == "OWNER" or values["system_role"] == "OWNER")
        ):
            fail(403, "Không được đổi quyền OWNER", "forbidden")
        if target.system_role == "OWNER":
            owners = await db.scalar(
                select(func.count()).select_from(User).where(User.system_role == "OWNER")
            )
            if (owners or 0) <= 1:
                fail(409, "Hệ thống phải còn ít nhất 1 OWNER", "last_owner")
    if target.system_role == "OWNER" and user.id != target.id and user.system_role != "OWNER":
        fail(403, "Không được sửa OWNER", "forbidden")
    if password := values.pop("password", None):
        try:
            target.password_hash = await hash_password(password.get_secret_value())
        except ValueError:
            fail(422, "Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte", "validation_error")
    for key, value in values.items():
        setattr(target, key, value)
    target.avatar_initials = initials(target.display_name)
    await commit(db)
    return target
