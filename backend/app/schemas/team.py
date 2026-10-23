from uuid import UUID

from pydantic import Field

from app.schemas.common import Input, Name, Record


class TeamAgents(Input):
    agent_ids: list[UUID] = Field(min_length=1)


class TeamCreate(TeamAgents):
    name: Name
    description: str = ""
    icon: str = Field(default="🤖", max_length=8)
    logo_url: str | None = Field(default=None, max_length=300, pattern=r"^/api/assets/logos/[a-f0-9-]+\.png$")


class TeamPatch(Input):
    name: Name | None = None
    description: str | None = None
    icon: str | None = Field(default=None, max_length=8)
    logo_url: str | None = Field(default=None, max_length=300, pattern=r"^/api/assets/logos/[a-f0-9-]+\.png$")
    agent_ids: list[UUID] | None = Field(default=None, min_length=1)


class TeamOut(Record):
    name: str
    description: str
    icon: str
    logo_url: str | None
    agent_ids: list[UUID]
