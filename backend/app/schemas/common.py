from datetime import datetime
from typing import Annotated, Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class ErrorResponse(BaseModel):
    detail: str
    code: str


Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: int
    next_cursor: str | None = None


class Success(BaseModel):
    ok: bool = True


class PreferenceInput(Input):
    key: str = Field(min_length=1, max_length=60)
    value: Any
