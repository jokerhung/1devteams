from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.deps import DB, CurrentUser, fail
from app.core.security import access_token, verify_password
from app.db.models import User
from app.schemas.user import Login, LoginOut, UserOut

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginOut)
async def login(body: Login, request: Request, db: DB):
    user = await db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not user or not await verify_password(body.password.get_secret_value(), user.password_hash):
        fail(401, "Email hoặc mật khẩu không đúng", "invalid_credentials")
    return {"access_token": access_token(user.id, request.app.state.settings), "user": user}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
