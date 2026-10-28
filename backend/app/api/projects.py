import asyncio
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import delete, func, select

from app.core.deps import DB, CurrentUser, fail, record, require_project
from app.db.models import Agent, Project, ProjectMember, Team, Ticket, User, Workflow
from app.schemas.agent import AgentOut
from app.schemas.common import Page, Success
from app.schemas.project import (
    MemberCreate,
    MemberOut,
    MemberRolePatch,
    MembersOut,
    ProjectCreate,
    ProjectOut,
    ProjectPatch,
    ProjectTree,
    SeedDefaultOut,
    WorkspaceInput,
    WorkspaceOut,
)
from app.services.agent_service import public_agent
from app.services.common import commit, fields, patch_values
from app.services.project_service import effective_agents, guard_removed_agents, visible_projects
from app.services.seed import DEFAULT_TEAM, template_graph
from app.services.team_service import public_team
from app.services.workspace_validator import validate_workspace

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/validate-workspace", response_model=WorkspaceOut)
async def workspace(body: WorkspaceInput, request: Request, user: CurrentUser):
    return await validate_workspace(body.path, request.app.state.settings)


@router.get("/browse-workspace")
async def browse_workspace(request: Request, user: CurrentUser, path: str = "") -> dict[str, Any]:
    """Browse directories on the backend host, restricted to configured workspace roots."""

    def listing() -> dict[str, Any]:
        roots = request.app.state.settings.workspace_roots
        if not path:
            return {
                "path": None,
                "parent": None,
                "directories": [{"name": str(root), "path": str(root)} for root in roots if root.is_dir()],
            }
        folder = Path(path)
        if not folder.is_absolute():
            fail(422, "Đường dẫn phải là đường dẫn tuyệt đối", "invalid_workspace")
        folder = folder.resolve()
        if not any(folder.is_relative_to(root) for root in roots):
            fail(403, "Ngoài thư mục cho phép", "invalid_workspace")
        if not folder.is_dir():
            fail(404, "Không tìm thấy thư mục", "not_found")
        directories = []
        for child in folder.iterdir():
            try:
                resolved = child.resolve()
                if child.is_dir() and any(resolved.is_relative_to(root) for root in roots):
                    directories.append({"name": child.name, "path": str(resolved)})
            except OSError:
                continue
        parent = folder.parent
        return {
            "path": str(folder),
            "parent": str(parent)
            if parent != folder and any(parent.is_relative_to(r) for r in roots)
            else None,
            "directories": sorted(directories, key=lambda entry: entry["name"].casefold()),
        }

    try:
        return await asyncio.to_thread(listing)
    except OSError:
        fail(403, "Không đọc được thư mục", "directory_unreadable")


def allowed_file_root(request: Request, root: str) -> str:
    folder = Path(root)
    if not folder.is_absolute():
        fail(403, "Thư mục không được phép", "invalid_workspace")
    folder = folder.resolve()
    if folder not in request.app.state.settings.workspace_roots:
        fail(403, "Thư mục không được phép", "invalid_workspace")
    return str(folder)


@router.get("/workspace-files")
async def allowed_workspace_files(
    request: Request,
    user: CurrentUser,
    root: str = Query(default="", max_length=4000),
    path: str = Query(default="", max_length=2000),
) -> dict:
    from app.services.workspace_files import list_workspace_files

    def listing() -> dict:
        roots = request.app.state.settings.workspace_roots
        if not root:
            if path:
                fail(403, "Chọn thư mục được phép trước", "invalid_workspace")
            return {
                "path": "",
                "entries": [
                    {"name": str(folder), "path": str(folder), "kind": "directory"}
                    for folder in roots
                    if folder.is_dir()
                ],
                "truncated": False,
            }
        return list_workspace_files(allowed_file_root(request, root), roots, path)

    try:
        return await asyncio.to_thread(listing)
    except (OSError, ValueError):
        fail(400, "Không đọc được thư mục", "directory_unreadable")


@router.get("/workspace-file")
async def allowed_workspace_file(
    request: Request,
    user: CurrentUser,
    root: str = Query(min_length=1, max_length=4000),
    path: str = Query(min_length=1, max_length=2000),
) -> dict:
    from app.services.workspace_files import read_workspace_file

    def read() -> dict:
        return read_workspace_file(
            allowed_file_root(request, root), request.app.state.settings.workspace_roots, path
        )

    try:
        return await asyncio.to_thread(read)
    except (OSError, ValueError):
        fail(400, "Không đọc được file", "file_unreadable")


@router.get("/recent", response_model=list[ProjectOut])
async def recent_projects(
    db: DB, user: CurrentUser, limit: int = Query(default=5, ge=1, le=100), pin: UUID | None = None
):
    projects = list(
        (
            await db.scalars(
                visible_projects(user).order_by(Project.last_activity_at.desc(), Project.id).limit(limit)
            )
        ).all()
    )
    if pin and str(pin) not in {project.id for project in projects}:
        project = await require_project(db, str(pin), user)
        projects = projects[: limit - 1] + [project]
    return projects


@router.get("", response_model=Page[ProjectOut])
async def list_projects(
    db: DB,
    user: CurrentUser,
    sort: Literal["recent", "name"] = "recent",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    query = visible_projects(user)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    query = (
        query.order_by(Project.last_activity_at.desc(), Project.id)
        if sort == "recent"
        else query.order_by(Project.name)
    )
    projects = (await db.scalars(query.limit(limit).offset(offset))).all()
    return {
        "items": [ProjectOut.model_validate(item).model_dump(mode="json") for item in projects],
        "total": total,
    }


async def valid_path(path: str, request: Request) -> str:
    result = await validate_workspace(path, request.app.state.settings)
    if not result.exists or not result.within_allowed_roots or not result.is_git_repo:
        fail(
            400, "Workspace phải là thư mục Git tuyệt đối trong ALLOWED_WORKSPACE_ROOTS", "invalid_workspace"
        )
    return str(await asyncio.to_thread(Path(path).resolve))


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, request: Request, db: DB, user: CurrentUser):
    values = body.model_dump()
    values["workspace_path"] = await valid_path(body.workspace_path, request)
    entity = Project(**values, owner_id=user.id)
    db.add(entity)
    await commit(db)
    return entity


@router.get("/{pid}", response_model=ProjectOut)
async def get_project(pid: UUID, db: DB, user: CurrentUser):
    return await require_project(db, str(pid), user)


@router.get("/{pid}/files")
async def workspace_files(
    pid: UUID, request: Request, db: DB, user: CurrentUser, path: str = Query(default="", max_length=2000)
) -> dict:
    from app.services.workspace_files import list_workspace_files

    project = await require_project(db, str(pid), user)
    try:
        return await asyncio.to_thread(
            list_workspace_files, project.workspace_path, request.app.state.settings.workspace_roots, path
        )
    except (OSError, ValueError):
        fail(400, "Không đọc được thư mục workspace", "directory_unreadable")


@router.get("/{pid}/file")
async def workspace_file(
    pid: UUID, request: Request, db: DB, user: CurrentUser, path: str = Query(min_length=1, max_length=2000)
) -> dict:
    from app.services.workspace_files import read_workspace_file

    project = await require_project(db, str(pid), user)
    try:
        return await asyncio.to_thread(
            read_workspace_file, project.workspace_path, request.app.state.settings.workspace_roots, path
        )
    except (OSError, ValueError):
        fail(400, "Không đọc được file workspace", "file_unreadable")


@router.patch("/{pid}", response_model=ProjectOut)
async def patch_project(pid: UUID, body: ProjectPatch, request: Request, db: DB, user: CurrentUser):
    entity = await require_project(db, str(pid), user, write=True)
    values = patch_values(body)
    if "workspace_path" in values:
        values["workspace_path"] = await valid_path(values["workspace_path"], request)
    for key, value in values.items():
        setattr(entity, key, value)
    await commit(db)
    return entity


@router.delete("/{pid}", response_model=Success)
async def delete_project(pid: UUID, request: Request, db: DB, user: CurrentUser):
    from app.services.assets import attachment_paths, remove_ticket_files

    project = await require_project(db, str(pid), user, write=True)
    ticket_ids = list((await db.scalars(select(Ticket.id).where(Ticket.project_id == project.id))).all())
    runner = request.app.state.ticket_runner
    if any(tid in runner.tasks or tid in runner.adhoc_tasks for tid in ticket_ids):
        fail(409, "Project đang có agent hoạt động")
    paths = await attachment_paths(db, ticket_ids)
    running = await db.scalar(
        select(Ticket.id)
        .where(
            Ticket.project_id == project.id,
            Ticket.status.in_(["RUNNING", "WAITING_USER_INPUT", "WAITING_USER_CONFIRM"]),
        )
        .limit(1)
    )
    if running:
        fail(409, "Hãy dừng ticket đang chạy trước khi xóa project", "project_in_use")
    await db.execute(delete(Ticket).where(Ticket.project_id == project.id))
    await db.execute(delete(Workflow).where(Workflow.project_id == project.id))
    await db.delete(project)
    await commit(db)
    await remove_ticket_files(request.app.state.settings, ticket_ids, paths)
    for tid in ticket_ids:
        await runner.checkpointer.adelete_thread(tid)
    return {"ok": True}


@router.get("/{pid}/members", response_model=MembersOut)
async def members(pid: UUID, db: DB, user: CurrentUser) -> dict:
    await require_project(db, str(pid), user)
    result: dict[str, list[dict]] = {"users": [], "agents": [], "teams": []}
    for member in (await db.scalars(select(ProjectMember).where(ProjectMember.project_id == str(pid)))).all():
        model: Any = {"USER": User, "AGENT": Agent, "TEAM": Team}[member.member_type]
        entity = await db.get(model, member.member_id)
        if entity is None:
            continue
        if member.member_type == "USER":
            from app.schemas.user import UserOut

            value = UserOut.model_validate(entity).model_dump(mode="json")
        elif member.member_type == "AGENT":
            value = public_agent(entity)
        else:
            value = await public_team(db, entity)
        value["project_role"] = member.project_role
        result[{"USER": "users", "AGENT": "agents", "TEAM": "teams"}[member.member_type]].append(value)
    return result


@router.post("/{pid}/members", response_model=MemberOut, status_code=201)
async def add_member(pid: UUID, body: MemberCreate, db: DB, user: CurrentUser) -> dict:
    await require_project(db, str(pid), user, write=True)
    model: Any = {"USER": User, "AGENT": Agent, "TEAM": Team}[body.member_type]
    entity = await record(db, model, body.member_id)
    if body.member_type == "AGENT" and not entity.is_active:
        fail(422, "Agent đã vô hiệu hóa", "validation_error")
    member = ProjectMember(
        project_id=str(pid),
        member_type=body.member_type,
        member_id=str(body.member_id),
        project_role=body.project_role,
    )
    db.add(member)
    await commit(db)
    return fields(member)


@router.delete("/{pid}/members/{member_type}/{member_id}", response_model=Success)
async def remove_member(
    pid: UUID, member_type: Literal["USER", "AGENT", "TEAM"], member_id: UUID, db: DB, user: CurrentUser
):
    await require_project(db, str(pid), user, write=True)
    before = {agent.id for agent in await effective_agents(db, str(pid))}
    await db.execute(
        delete(ProjectMember).where(
            ProjectMember.project_id == str(pid),
            ProjectMember.member_type == member_type,
            ProjectMember.member_id == str(member_id),
        )
    )
    await guard_removed_agents(db, str(pid), before)
    await commit(db)
    return {"ok": True}


@router.patch("/{pid}/members/USER/{member_id}", response_model=Success)
async def patch_member_role(pid: UUID, member_id: UUID, body: MemberRolePatch, db: DB, user: CurrentUser):
    await require_project(db, str(pid), user, write=True)
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == str(pid),
            ProjectMember.member_type == "USER",
            ProjectMember.member_id == str(member_id),
        )
    )
    if member is None:
        fail(404, "Không tìm thấy thành viên", "not_found")
    member.project_role = body.project_role
    await commit(db)
    return {"ok": True}


@router.get("/{pid}/effective-agents", response_model=list[AgentOut])
async def project_agents(pid: UUID, db: DB, user: CurrentUser) -> list[dict]:
    await require_project(db, str(pid), user)
    return [public_agent(agent) for agent in await effective_agents(db, str(pid))]


@router.post("/{pid}/seed-default", response_model=SeedDefaultOut)
async def seed_default(pid: UUID, db: DB, user: CurrentUser) -> dict:
    await require_project(db, str(pid), user, write=True)
    team = await db.scalar(select(Team).where(Team.name == DEFAULT_TEAM))
    if team is None:
        fail(409, "Team mặc định không còn tồn tại", "missing_default_team")
    member = await db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == str(pid),
            ProjectMember.member_type == "TEAM",
            ProjectMember.member_id == team.id,
        )
    )
    if member is None:
        db.add(ProjectMember(project_id=str(pid), member_type="TEAM", member_id=team.id))
        await db.flush()
    from app.services.workflow_service import publish, revalidate

    workflow = await db.scalar(
        select(Workflow).where(Workflow.project_id == str(pid), Workflow.ticket_prefix == "BUG")
    )
    if workflow is None:
        workflow = Workflow(
            project_id=str(pid),
            name="Fix Bug",
            ticket_prefix="BUG",
            graph=template_graph("bugfix_default", await effective_agents(db, str(pid))).model_dump(),
        )
        db.add(workflow)
        await db.flush()
        await revalidate(db, workflow)
        await publish(db, workflow, user.id)
    elif workflow.name != "Fix Bug":
        fail(409, "Prefix BUG đang được dùng bởi workflow khác", "conflict")
    elif workflow.status != "PUBLISHED":
        if workflow.status == "ARCHIVED":
            fail(409, "Workflow Fix Bug đã archived; hãy khôi phục trước", "workflow_archived")
        await publish(db, workflow, user.id)
    await commit(db)
    from app.schemas.workflow import WorkflowOut

    return {
        "team": await public_team(db, team),
        "workflow": WorkflowOut.model_validate(workflow).model_dump(mode="json"),
    }


@router.get("/{pid}/tree", response_model=ProjectTree)
async def tree(pid: UUID, db: DB, user: CurrentUser) -> dict:
    project = await require_project(db, str(pid), user)
    from app.services.ticket_service import public_ticket

    workflows = (
        await db.scalars(
            select(Workflow)
            .where(Workflow.project_id == str(pid))
            .order_by(Workflow.position, Workflow.created_at)
        )
    ).all()
    result = []
    for workflow in workflows:
        tickets = (
            await db.scalars(
                select(Ticket)
                .where(Ticket.workflow_id == workflow.id)
                .order_by(Ticket.updated_at.desc(), Ticket.id)
                .limit(15)
            )
        ).all()
        result.append(
            {
                "id": workflow.id,
                "name": workflow.name,
                "prefix": workflow.ticket_prefix,
                "status": workflow.status,
                "tickets": [await public_ticket(db, ticket) for ticket in tickets],
            }
        )
    return {"project": ProjectOut.model_validate(project).model_dump(mode="json"), "workflows": result}
