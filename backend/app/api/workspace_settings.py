from typing import Annotated

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.deps import Admin, fail

router = APIRouter(prefix="/settings/workspaces", tags=["Settings"])


class WorkspaceRoots(BaseModel):
    roots: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(min_length=1, max_length=100)


@router.get("", response_model=WorkspaceRoots)
async def get_workspace_roots(request: Request, user: Admin):
    return WorkspaceRoots(roots=request.app.state.workspace_settings.roots())


@router.put("", response_model=WorkspaceRoots)
async def set_workspace_roots(body: WorkspaceRoots, request: Request, user: Admin):
    try:
        roots = await request.app.state.workspace_settings.save(body.roots)
    except ValueError as error:
        fail(422, str(error), "invalid_workspace")
    except OSError:
        fail(503, "Không lưu được cấu hình thư mục. Kiểm tra quyền ghi của backend.")
    return WorkspaceRoots(roots=roots)
