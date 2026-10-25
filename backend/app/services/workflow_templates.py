"""Reusable workflow definitions, bound to project agents when instantiated."""

from typing import Any

from sqlalchemy import select

from app.db.models import Agent, WorkflowTemplate
from app.schemas.workflow import Graph

FEATURE_STEPS = [
    (
        "leader",
        "COORDINATOR",
        "@leader",
        "Tiếp nhận & điều phối",
        (
            "Tiếp nhận yêu cầu user, xác định phạm vi, tiêu chí nghiệm thu và phân công BA, "
            "Designer, Planner, Developer, Tester. Nếu thiếu thông tin, hỏi user; nếu đủ, chuyển "
            "BA."
        ),
        None,
    ),
    (
        "ba",
        "BA",
        "@ba",
        "Phân tích yêu cầu",
        (
            "Phân tích yêu cầu khách hàng thành Markdown: mục tiêu, user story, phạm vi, business "
            "rules, acceptance criteria, trường hợp biên. Đọc mã nguồn để xác minh ngữ cảnh. Trả "
            "đầy đủ nội dung tài liệu; hệ thống lưu vào docs/ theo ticket."
        ),
        "requirements.md",
    ),
    (
        "designer",
        "DESIGNER",
        "@designer",
        "Thiết kế giao diện",
        (
            "Dựa trên requirements.md, thiết kế giao diện dưới dạng Markdown: cấu trúc màn hình, "
            "wireframe bằng text, thành phần, trạng thái loading/empty/error, luồng tương tác, "
            "responsive và accessibility. Trả đầy đủ tài liệu để lưu trong docs/."
        ),
        "design.md",
    ),
    (
        "planner",
        "PLANNER",
        "@planner",
        "Lập implementation plan",
        (
            "Đọc requirements.md và design.md trong thư mục docs/ của ticket, đối chiếu code hiện "
            "có và viết implementation plan Markdown: các bước, file/module, phụ thuộc, rủi ro, "
            "tiêu chí hoàn thành. Trả đầy đủ nội dung để lưu trong docs/."
        ),
        "implementation-plan.md",
    ),
    (
        "test_cases",
        "TESTER",
        "@tester",
        "Viết system test case",
        (
            "Dựa trên các tài liệu docs/ của ticket, viết test case Markdown CHỈ cho system test "
            "end-to-end: ID, điều kiện, dữ liệu, thao tác, kết quả mong đợi, acceptance criteria. "
            "Không viết unit/integration test. Chưa chạy test ở bước này. Trả đầy đủ tài liệu để "
            "lưu trong docs/."
        ),
        "system-test-cases.md",
    ),
    (
        "developer",
        "DEVELOPER",
        "@developer",
        "Triển khai tính năng",
        (
            "Đọc toàn bộ file Markdown trong docs/ của ticket: requirements.md, design.md, "
            "implementation-plan.md, system-test-cases.md. Thực hiện code đúng plan; nếu tester/user "
            "báo lỗi thì sửa và báo lại. Không commit/push. Tóm tắt file thay đổi và hướng dẫn "
            "chạy hệ thống."
        ),
        None,
    ),
    (
        "tester",
        "TESTER",
        "@tester",
        "System test & báo cáo user",
        (
            "CHỈ thực hiện system test theo system-test-cases.md của ticket trên ứng dụng chạy "
            "thật; không thay bằng unit/integration test. Ghi từng case PASS/FAIL/BLOCKED, bằng "
            "chứng và lỗi thực tế. Không tuyên bố pass khi chưa chạy; có FAIL/BLOCKED thì trả fail"
            " và mô tả cho developer. Báo kết quả đầy đủ cho user dưới dạng Markdown để lưu docs/."
        ),
        "system-test-report.md",
    ),
    (
        "devops",
        "LEADER",
        "@devops",
        "Commit & push",
        (
            "Sau khi user xác nhận, review thay đổi và tài liệu docs/ của ticket; chốt danh sách "
            "file cần commit, loại secrets/log/build artifact, chốt Conventional Commit message. "
            "Trả @@RELEASE để backend commit/push đúng danh sách. Không phát hành trước xác nhận."
        ),
        None,
    ),
]


def feature_graph(agents: list[Agent]) -> Graph:
    roles = {a.role_key: a.id for a in agents if a.is_active}
    specs: list[tuple[str, str, dict[str, Any]]] = [("start", "start", {})]
    for key, role, _handle, title, instruction, document in FEATURE_STEPS:
        data: dict[str, Any] = {
            "agent_id": roles.get(role),
            "label": title,
            "instructions": instruction,
            "routing": "none",
        }
        if key in {"leader", "ba"}:
            data["routing"] = "ba"
        if key == "tester":
            data["routing"] = "tester"
        if key == "developer":
            data["requires_write"] = True
        if document:
            data["document_name"] = document
        specs.append(("n_" + key, "git_release" if key == "devops" else "agent", data))
    specs += [
        ("g_leader", "human_input", {"label": "Leader hỏi rõ yêu cầu"}),
        ("g_ba", "human_input", {"label": "BA hỏi rõ yêu cầu"}),
        (
            "g_confirm",
            "human_confirm",
            {"message": "Bạn xác nhận tính năng và kết quả system test để @devops commit & push?"},
        ),
        ("end", "end", {}),
    ]
    links = [
        ("start", "n_leader", None),
        ("n_leader", "g_leader", "need_info"),
        ("g_leader", "n_leader", None),
        ("n_leader", "n_ba", "ready"),
        ("n_ba", "g_ba", "need_info"),
        ("g_ba", "n_ba", None),
        ("n_ba", "n_designer", "ready"),
        ("n_designer", "n_planner", None),
        ("n_planner", "n_test_cases", None),
        ("n_test_cases", "n_developer", None),
        ("n_developer", "n_tester", None),
        ("n_tester", "n_developer", "fail"),
        ("n_tester", "g_confirm", "pass"),
        ("g_confirm", "n_devops", "approved"),
        ("g_confirm", "n_developer", "rejected"),
        ("n_devops", "end", "success"),
    ]
    return Graph.model_validate(
        {
            "nodes": [
                {"id": key, "type": kind, "data": data, "position": {"x": i * 180, "y": 0}}
                for i, (key, kind, data) in enumerate(specs)
            ],
            "edges": [
                {"id": f"e{i}", "source": s, "target": t, "sourceHandle": h}
                for i, (s, t, h) in enumerate(links)
            ],
        }
    )


async def configured_graph(db, name: str, agents: list[Agent]) -> Graph:
    from app.services.seed import template_graph

    graph = template_graph(name, agents)
    config = await db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.key == name))
    if config:
        if config.graph:
            graph = Graph.model_validate(config.graph)
            roles = {agent.role_key: agent.id for agent in agents if agent.is_active}
            handles = {agent.handle: agent.id for agent in agents if agent.is_active}
            for node in graph.nodes:
                if node.type in {"agent", "git_release"}:
                    role = str(node.data.get("agent_role", ""))
                    node.data["agent_id"] = handles.get(str(node.data.get("agent_handle", ""))) or (
                        roles.get(role) if role != "CUSTOM" else None
                    )
        for node in graph.nodes:
            if node.id in config.instructions:
                node.data["instructions"] = config.instructions[node.id]
    return graph
