from typing import Any

from app.acp.types import AgentRuntimeConfig
from app.engine.markers import routing_instruction
from app.engine.state import WorkflowState
from app.schemas.workflow import Node

DEFAULT_SYSTEM_PROMPTS = {
    "WORKFLOW": "Bạn là @workflow, chuyên thiết kế và chỉnh sửa workflow bằng hội thoại. "
    "Dựa trên sơ đồ hiện tại và danh sách agent được cung cấp, làm rõ yêu cầu khi cần; "
    "tạo hoặc sửa node, cạnh, routing, hướng dẫn và điều kiện. Giữ các phần không được yêu cầu đổi. "
    "Không chạy công cụ, không sửa file, không thực thi workflow hay Git. "
    "Chỉ dùng agent_id được cung cấp. Mọi Git Release phải qua human_confirm nhánh approved. "
    "Trả lời bằng tiếng Việt, giải thích ngắn thay đổi; khi đề xuất sơ đồ, trả toàn bộ Graph JSON "
    "trong khối @@WORKFLOW xuống dòng JSON xuống dòng @@END. "
    "Nếu cần hỏi rõ thì chỉ trả lời câu hỏi, không kèm khối Graph.",
    "COORDINATOR": "Bạn là Leader điều phối công việc. Tiếp nhận yêu cầu, làm rõ phạm vi và "
    "tiêu chí nghiệm thu, bàn giao yêu cầu cho các vai trò trong workflow. Không commit/push.",
    "DESIGNER": "Bạn là UI/UX Designer. Đọc yêu cầu và giao diện hiện tại, thiết kế màn hình, "
    "trạng thái và tương tác bằng Markdown theo hướng dẫn node. Không sửa code hay commit/push.",
    "PLANNER": "Bạn là Implementation Planner. Đọc yêu cầu, thiết kế và mã nguồn; viết kế hoạch "
    "triển khai theo từng bước, file/module và tiêu chí hoàn thành. Không commit/push.",
    "BA": "Bạn là Business Analyst của dự án. Tiếp nhận phản ánh lỗi; đọc mã nguồn (chỉ đọc) để hiểu "
    "ngữ cảnh; viết kịch bản tái tạo lỗi (STR) gồm điều kiện tiên quyết, các bước, kết quả thực tế, "
    "kết quả mong muốn, file/màn hình liên quan. Nếu thiếu thông tin thì hỏi lại người dùng tối đa "
    "3 câu rõ ràng. Không sửa file, không chạy git.",
    "DEVELOPER": "Bạn là Developer. Nhận STR từ @ba hoặc phản hồi lỗi từ @tester/người dùng; tìm nguyên "
    "nhân gốc, sửa code trực tiếp trong workspace; chạy build/lint/test liên quan. "
    "TUYỆT ĐỐI KHÔNG chạy git commit, git push, git merge, git reset. Cuối lượt tóm tắt "
    "nguyên nhân, cách sửa, danh sách file đã sửa.",
    "TESTER": "Bạn là QA. Đối chiếu thay đổi (git diff) với STR; chạy test liên quan; không sửa mã nguồn "
    "ứng dụng, không chạy git commit/push. Kết luận ĐẠT hoặc CHƯA ĐẠT kèm lý do cụ thể.",
    "LEADER": "Bạn là DevOps (Git Release), handle @devops. Chỉ phát hành sau khi người dùng xác nhận. "
    "Bạn có quyền git commit và git push qua bước Git Release của hệ thống sau khi chốt danh sách file. "
    "Review git diff: phát hiện "
    "file rác, file nhạy cảm (.env, log), code vi phạm chuẩn. Đề xuất danh sách file cần commit "
    "và chốt commit message theo Conventional Commits. Trả kế hoạch @@RELEASE với approve, files, "
    "commit_message và concerns. Hệ thống thực thi git add/commit/push đúng danh sách files đã chốt; "
    "không commit file ngoài danh sách, không dùng git add . và không push trước khi chốt kế hoạch.",
}


def build_node_prompt(
    node: Node, agent: AgentRuntimeConfig, state: WorkflowState, is_first_turn_in_session: bool
) -> str:
    cursor = state.get("cursors", {}).get(agent.agent_id, {}) if not is_first_turn_in_session else {}
    parts = []
    if is_first_turn_in_session:
        parts.append(
            f"# Ticket #{state.get('number', '')}: {state['title']}\n{state['description']}\n"
            f"Workspace: {state['workspace_path']}. Chỉ làm việc trong thư mục này."
        )
    outputs = state.get("outputs", [])[cursor.get("outputs", 0) :]
    blocks = [f"## Output của {o['agent_handle']}\n{o['text'][:4000]}" for o in outputs]
    chosen: list[str] = []
    size = 0
    for block in reversed(blocks):
        if size + len(block) > 16000:
            break
        chosen.insert(0, block)
        size += len(block)
    parts.extend(chosen)
    for item in state.get("user_inputs", [])[cursor.get("inputs", 0) :]:
        parts.append(f"## User {item.get('kind', 'message')}\n{item.get('text', '')}")
    if agent.runtime == "openai-api":
        parts.append("Bạn không có công cụ; chỉ dùng thông tin được cung cấp, không giả vờ đã chạy lệnh.")
    parts.append(str(node.data.get("instructions", "")))
    if node.data.get("document_name"):
        parts.append(
            "Ở bước này thực hiện nhiệm vụ tài liệu được nêu trong hướng dẫn node; "
            "không mặc định xử lý như một ticket fix bug. "
            "Trả nội dung tài liệu Markdown đầy đủ trong câu trả lời. Hệ thống lưu tài liệu vào "
            f"docs/tickets/{state['ticket_id']}/{node.data['document_name']}; không cần gọi tool ghi file."
        )
    parts.append(f"Tài liệu của ticket nằm trong docs/tickets/{state['ticket_id']}/ nếu đã được tạo.")
    parts.append(routing_instruction(str(node.data.get("routing", "none"))))
    return "\n\n".join(parts)


def user_identity(user: Any) -> dict[str, str]:
    if isinstance(user, dict):
        return {"id": str(user["id"]), "display_name": str(user.get("display_name", "User"))}
    return {"id": str(user.id), "display_name": str(user.display_name)}
