"""Portable templates bind roles/handles to project agent IDs, then snapshot the result."""

from sqlalchemy import select

from app.db.models import WorkflowTemplate
from app.schemas.orchestrator_template import OrchestratorTemplateInput, OrchestratorTemplateOut
from app.schemas.workflow import OrchestratorConfig, OrchestratorWorker

FEATURE_INSTRUCTIONS = """Bạn là Leader (Orchestrator) điều phối dự án phần mềm gồm 5 thành viên:
- 'ba': Phân tích yêu cầu của user thành đặc tả kỹ thuật & edge cases.
- 'planner': Thiết kế cấu trúc hàm/class và luồng xử lý từ đặc tả của BA.
- 'designer': Thiết kế giao diện người dùng bằng file Markdown.
- 'developer': Viết code hoặc sửa lỗi dựa trên thiết kế của Planner và báo cáo từ Tester.
- 'tester': Kiểm thử, review code của Developer đối chiếu với yêu cầu của BA.

QUY TẮC ĐIỀU PHỐI:
1. Quy trình chuẩn: ba -> planner -> designer -> developer -> tester.
2. Chỉ chuyển sang designer nếu cần thiết kế màn hình mới; nếu không, chuyển file plan thẳng sang developer.
3. Nếu tester báo FAIL, gọi lại developer sửa lỗi rồi chuyển tester kiểm thử lại.
4. Nếu tester báo PASS, chọn FINISH để bàn giao cho khách hàng. Không coi kiểm thử chưa thực hiện là PASS.
5. Tất cả các bước nếu cần xác nhận phải hỏi lại người tạo ticket và chờ trả lời, không tự suy đoán đồng ý.
6. Chia sẻ requirements.md, implementation-plan.md, design.md (nếu có), test-report.md giữa các thành viên.
Không tự commit hoặc push code."""

DEFAULT_FEATURE = OrchestratorTemplateInput(
    name="Add new feature",
    description=(
        "Leader điều phối BA → Planner → Designer khi cần màn hình mới → Developer → Tester. "
        "FAIL thì sửa lại; PASS thì bàn giao."
    ),
    instructions=FEATURE_INSTRUCTIONS,
    workers=[
        {
            "role_key": "BA",
            "agent_handle": "@ba",
            "instructions": (
                "Phân tích yêu cầu thành đặc tả Markdown: input, output, business rules, acceptance "
                "criteria và edge cases. Nếu thiếu thông tin hãy hỏi người tạo ticket."
            ),
            "document_name": "requirements.md",
        },
        {
            "role_key": "PLANNER",
            "agent_handle": "@planner",
            "instructions": (
                "Đọc requirements.md và mã nguồn. Viết plan Markdown: cấu trúc hàm/class, file cần sửa, "
                "luồng xử lý, các bước triển khai. Chỉ rõ có cần màn hình mới hay không; "
                "chưa viết code hoàn chỉnh."
            ),
            "document_name": "implementation-plan.md",
        },
        {
            "role_key": "DESIGNER",
            "agent_handle": "@designer",
            "instructions": (
                "Chỉ thực hiện khi cần thiết kế màn hình mới. Dựa trên requirements và plan, trả tài liệu "
                "Markdown: cấu trúc màn hình, wireframe text, thành phần, luồng tương tác, "
                "loading/empty/error, responsive và accessibility."
            ),
            "document_name": "design.md",
        },
        {
            "role_key": "DEVELOPER",
            "agent_handle": "@developer",
            "instructions": (
                "Đọc requirements.md, implementation-plan.md và design.md nếu có. Viết hoặc sửa code "
                "theo plan và báo cáo lỗi của Tester. Báo file thay đổi và bằng chứng thực tế. "
                "Không commit/push."
            ),
        },
        {
            "role_key": "TESTER",
            "agent_handle": "@tester",
            "instructions": (
                "Kiểm thử thực tế và review code đối chiếu requirements, acceptance criteria, edge cases. "
                "Mở đầu STATUS: PASS hoặc STATUS: FAIL; nếu chưa chạy test ghi STATUS: BLOCKED. "
                "Nêu bằng chứng và lỗi cụ thể để Developer sửa."
            ),
            "document_name": "test-report.md",
        },
    ],
)
DEFAULTS = {"add_feature": DEFAULT_FEATURE}
PREFIX = "orch:"


def validate_template_agents(template: OrchestratorTemplateInput, agents) -> None:
    active = [a for a in agents if a.is_active and a.role_key != "WORKFLOW"]
    selected = set()
    references = [(template.coordinator_role, template.coordinator_handle)] + [
        (worker.role_key, worker.agent_handle) for worker in template.workers
    ]
    for role, handle in references:
        candidates = [a for a in active if a.role_key == role and (not handle or a.handle == handle)]
        if len(candidates) != 1 or candidates[0].id in selected:
            raise ValueError("Chọn agent có sẵn, đang hoạt động và không trùng nhau cho template")
        selected.add(candidates[0].id)


async def template_definitions(db) -> dict[str, OrchestratorTemplateInput]:
    result = dict(DEFAULTS)
    rows = (await db.scalars(select(WorkflowTemplate).where(WorkflowTemplate.key.startswith(PREFIX)))).all()
    for row in rows:
        result[row.key[len(PREFIX) :]] = OrchestratorTemplateInput.model_validate(row.graph)
    return result


def bind_template(key: str, template: OrchestratorTemplateInput, agents=None) -> OrchestratorTemplateOut:
    out = OrchestratorTemplateOut(**template.model_dump(), id=key, builtin=key in DEFAULTS)
    if agents is None:
        return out
    active = [a for a in agents if a.is_active and a.role_key != "WORKFLOW"]
    used = set()

    def find(role, handle):
        candidates = [a for a in active if a.id not in used and a.role_key == role]
        agent = next((a for a in candidates if a.handle == handle), None)
        if agent is None and len(candidates) == 1:
            agent = candidates[0]
        if agent is None:
            out.missing_agents.append(f"{handle or role} ({role})")
        else:
            used.add(agent.id)
        return agent

    coordinator = find(template.coordinator_role, template.coordinator_handle)
    workers = []
    for worker in template.workers:
        agent = find(worker.role_key, worker.agent_handle)
        if agent:
            workers.append(
                OrchestratorWorker(
                    agent_id=agent.id, **worker.model_dump(exclude={"role_key", "agent_handle"})
                )
            )
    if not out.missing_agents and coordinator:
        out.orchestrator = OrchestratorConfig(
            coordinator_agent_id=coordinator.id,
            instructions=template.instructions,
            max_rounds=template.max_rounds,
            workers=workers,
        )
    return out
