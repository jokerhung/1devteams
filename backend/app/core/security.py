import asyncio
from datetime import UTC, datetime, timedelta

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from app.core.config import Settings


async def hash_password(password: str, *, allow_bootstrap_default: bool = False) -> str:
    # Only initial Owner seeding may use the explicitly requested installer default.
    is_bootstrap_default = allow_bootstrap_default and password == "123456"
    if (len(password) < 8 and not is_bootstrap_default) or len(password.encode()) > 72:
        raise ValueError("Mật khẩu cần ít nhất 8 ký tự và tối đa 72 byte")
    return (await asyncio.to_thread(bcrypt.hashpw, password.encode(), bcrypt.gensalt())).decode()


async def verify_password(password: str, hashed: str) -> bool:
    try:
        return await asyncio.to_thread(bcrypt.checkpw, password.encode(), hashed.encode())
    except ValueError:
        return False


def access_token(user_id: str, settings: Settings) -> str:
    return jwt.encode(
        {"sub": user_id, "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def token_subject(token: str, settings: Settings) -> str | None:
    try:
        value = jwt.decode(token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"])
        return str(value["sub"])
    except (JWTError, KeyError):
        return None


def cipher(settings: Settings) -> Fernet:
    if not settings.app_secret_key:
        raise ValueError("APP_SECRET_KEY chưa được cấu hình")
    try:
        return Fernet(settings.app_secret_key.get_secret_value().encode())
    except ValueError:
        raise ValueError("APP_SECRET_KEY phải là khóa Fernet hợp lệ") from None


def encrypt(value: str, settings: Settings) -> str:
    return cipher(settings).encrypt(value.encode()).decode()


def decrypt(value: str, settings: Settings) -> str:
    try:
        return cipher(settings).decrypt(value.encode()).decode()
    except InvalidToken:
        raise ValueError("Không giải mã được credential bằng APP_SECRET_KEY hiện tại") from None
