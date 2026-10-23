from typing import Literal

from pydantic import Field, SecretStr, field_validator

from app.schemas.common import Input, Name, Record

SystemRole = Literal["OWNER", "ADMIN", "MEMBER"]


class UserCreate(Input):
    email: str = Field(min_length=3, max_length=255, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    display_name: Name
    password: SecretStr
    system_role: SystemRole = "MEMBER"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class UserPatch(Input):
    display_name: Name | None = None
    password: SecretStr | None = None
    system_role: SystemRole | None = None


class UserOut(Record):
    email: str
    display_name: str
    system_role: SystemRole
    avatar_initials: str


class Login(Input):
    email: str = Field(max_length=255)
    password: SecretStr


class LoginOut(Input):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
