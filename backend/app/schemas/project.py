from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.agent import AgentOut
from app.schemas.common import Input, Name, Record
from app.schemas.team import TeamOut
from app.schemas.ticket import TicketOut
from app.schemas.user import UserOut
from app.schemas.workflow import WorkflowOut


class WorkspaceInput(Input):
    path: str = Field(min_length=1, max_length=500)


class WorkspaceOut(Input):
    exists: bool
    is_git_repo: bool
    current_branch: str | None
    remotes: list[str]
    dirty_files_count: int
    within_allowed_roots: bool


class ProjectCreate(Input):
    name: Name
    workspace_path: str = Field(min_length=1, max_length=500)
    default_branch: str = Field(min_length=1, max_length=200, pattern=r"^[^-\s][^\s]*$")
    description: str = ""
    git_remote: str = Field(default="origin", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")


class ProjectPatch(Input):
    name: Name | None = None
    workspace_path: str | None = Field(default=None, min_length=1, max_length=500)
    default_branch: str | None = Field(default=None, min_length=1, max_length=200, pattern=r"^[^-\s][^\s]*$")
    description: str | None = None
    git_remote: str | None = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")


class ProjectOut(Record):
    name: str
    description: str
    workspace_path: str
    default_branch: str
    git_remote: str
    owner_id: UUID
    next_ticket_number: int
    last_activity_at: datetime


class MemberCreate(Input):
    member_type: Literal["USER", "AGENT", "TEAM"]
    member_id: UUID
    project_role: Literal["MAINTAINER", "REPORTER", "VIEWER"] | None = None

    @model_validator(mode="after")
    def valid_role(self):
        if self.member_type == "USER" and self.project_role is None:
            self.project_role = "VIEWER"
        if self.member_type != "USER" and self.project_role is not None:
            raise ValueError("project_role chỉ áp dụng cho USER")
        return self


class UserMember(UserOut):
    project_role: str | None = None


class AgentMember(AgentOut):
    project_role: str | None = None


class TeamMember(TeamOut):
    project_role: str | None = None


class MembersOut(Input):
    users: list[UserMember]
    agents: list[AgentMember]
    teams: list[TeamMember]


class MemberOut(Record):
    project_id: UUID
    member_type: str
    member_id: UUID
    project_role: str | None


class MemberRolePatch(Input):
    project_role: Literal["MAINTAINER", "REPORTER", "VIEWER"]


class TreeWorkflow(Input):
    id: UUID
    name: str
    prefix: str
    status: str
    tickets: list[TicketOut]


class ProjectTree(Input):
    project: ProjectOut
    workflows: list[TreeWorkflow]


class SeedDefaultOut(Input):
    team: TeamOut
    workflow: WorkflowOut
