from pydantic import Field, field_validator

from app.schemas.common import Input, Name
from app.schemas.workflow import OrchestratorConfig, OrchestratorWorkerSettings


class TemplateWorker(OrchestratorWorkerSettings):
    role_key: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]+$")
    agent_handle: str = Field(default="", max_length=50, pattern=r"^(@[a-z0-9_-]{2,49})?$")


class OrchestratorTemplateInput(Input):
    name: Name
    description: str = Field(default="", max_length=2000)
    coordinator_role: str = Field(
        default="COORDINATOR", min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]+$"
    )
    coordinator_handle: str = Field(default="@leader", max_length=50, pattern=r"^(@[a-z0-9_-]{2,49})?$")
    instructions: str = Field(min_length=1, max_length=20000)
    max_rounds: int = Field(default=20, ge=1, le=40)
    workers: list[TemplateWorker] = Field(min_length=1, max_length=30)

    @field_validator("instructions")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nhập instruction cho Orchestrator")
        return value.strip()


class OrchestratorTemplateOut(OrchestratorTemplateInput):
    id: str
    builtin: bool = False
    orchestrator: OrchestratorConfig | None = None
    missing_agents: list[str] = Field(default_factory=list)
