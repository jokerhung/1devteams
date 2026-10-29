"""Route through the configured agent/runtime, retaining ticket tools and checkpoints."""

import json
import re
from collections.abc import Mapping
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.acp.types import AgentRuntimeConfig
from app.engine.nodes import gate, make_node
from app.engine.state import WorkflowState
from app.schemas.workflow import Graph, Node


def parse_decision(text: str, workers: Mapping[str, Any]) -> tuple[str, str]:
    block = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    payload = json.loads(block[1] if block else text.strip())
    if not isinstance(payload, dict):
        raise ValueError("Agent điều phối cần trả JSON next_worker/task_instruction")
    target, instruction = payload.get("next_worker"), payload.get("task_instruction")
    if (
        target not in {*workers, "FINISH", "ASK_USER"}
        or not isinstance(instruction, str)
        or not instruction.strip()
    ):
        raise ValueError("Agent điều phối chọn agent/nhiệm vụ không hợp lệ")
    return target, instruction[:20000]


def compile_orchestrator(graph: Graph, agents: dict[str, AgentRuntimeConfig], checkpointer: Any) -> Any:
    settings = graph.orchestrator
    if settings is None:
        raise ValueError("Missing Orchestrator configuration")
    workers = {node.id: node for node in graph.nodes if node.id.startswith("worker_")}
    leader = next(node for node in graph.nodes if node.id == "coordinator")
    roster = "\n".join(
        f"{key}: {agents[str(node.data['agent_id'])].handle} — {node.data.get('label', '')}"
        for key, node in workers.items()
    )

    async def coordinate(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        # All latest artifacts are shared explicitly, also after session reuse/restart.
        latest = {}
        for output in state.get("outputs", []):
            if output["node_id"] in workers:
                latest[output["node_id"]] = output["text"][-6000:]
        prompt = (
            f"{settings.instructions}\n\nBạn là Orchestrator. "
            "Chọn agent thực hiện dựa trên instruction và kết quả. "
            "Sau mỗi agent, đánh giá và giao bước tiếp. Nếu cần sửa lỗi hãy giao lại agent "
            "phù hợp; chỉ FINISH khi đã đáp ứng yêu cầu. Không tự commit/push. "
            "Nếu cần thông tin hoặc xác nhận từ người tạo ticket, chọn ASK_USER và ghi câu hỏi "
            "trong task_instruction. Phải chờ trả lời trước khi tiếp tục. "
            "Chỉ trả một JSON object, không kèm giải thích: "
            '{"next_worker":"worker_0 hoặc FINISH hoặc ASK_USER",'
            '"task_instruction":"chỉ thị cụ thể hoặc tổng kết bàn giao"}. '
            f"Chỉ dùng ID trong danh sách:\n{roster}\nArtifacts mới nhất:\n"
            + json.dumps(latest, ensure_ascii=False)
        )
        node = leader.model_copy(deep=True)
        node.data.update(instructions=prompt, max_iterations=settings.max_rounds)
        result = await make_node(node, agents)(state, config)
        target, instruction = parse_decision(result["outputs"][-1]["text"], workers)
        result["orchestrator_task"] = instruction
        result["last_route"] = state.get("last_route", {}) | {"coordinator": target}
        ctx = config["configurable"]["ctx"]
        recipient = (
            "Hoàn tất"
            if target == "FINISH"
            else "Người tạo ticket"
            if target == "ASK_USER"
            else agents[str(workers[target].data["agent_id"])].handle
        )
        await ctx.emit(
            "log",
            f"Orchestrator → {recipient}: {instruction}",
            node_id="coordinator",
            metadata={"next_worker": target},
        )
        if target == "FINISH":
            result["orchestrator_summary"] = instruction
        elif target == "ASK_USER":
            result["orchestrator_question"] = instruction
            result["orchestrator_resume"] = "coordinator"
        return result

    async def ask_user(state: WorkflowState, config: RunnableConfig) -> dict[str, Any]:
        ctx = config["configurable"]["ctx"]
        answer, counts = await gate(
            state,
            ctx,
            "orchestrator_input",
            "human_input",
            {
                "question": state["orchestrator_question"],
                "prompt_hint": "Chờ người tạo ticket xác nhận hoặc bổ sung thông tin.",
            },
        )
        return {
            "gate_counts": counts,
            "user_inputs": [
                {
                    "node_id": "orchestrator_input",
                    "kind": "answer",
                    "text": answer.get("text", ""),
                    "user": answer["user"],
                }
            ],
        }

    builder = StateGraph(WorkflowState)
    for node in graph.nodes:
        if node.id in {"start", "end"}:
            builder.add_node(node.id, make_node(node, agents))
    builder.add_node("coordinator", coordinate)
    builder.add_node("orchestrator_input", ask_user)
    builder.add_conditional_edges(
        "orchestrator_input",
        lambda state: state["orchestrator_resume"],
        {"coordinator": "coordinator", **{nid: nid for nid in workers}},
    )
    # Persist the route in state: error/retry updates must retain the pending worker.
    # Command-only destinations disappear when the runner updates checkpoint.error.
    builder.add_conditional_edges(
        "coordinator",
        lambda state: state["last_route"]["coordinator"],
        {**{nid: nid for nid in workers}, "FINISH": "end", "ASK_USER": "orchestrator_input"},
    )
    builder.add_edge(START, "start")
    builder.add_edge("start", "coordinator")
    builder.add_edge("end", END)
    for nid, worker in workers.items():

        async def execute(
            state: WorkflowState, config: RunnableConfig, node: Node = worker
        ) -> dict[str, Any]:
            assigned = node.model_copy(deep=True)
            latest = {}
            for output in state.get("outputs", []):
                if output["node_id"] in workers:
                    latest[output["node_id"]] = output["text"][-6000:]
            assigned.data["instructions"] = (
                f"Instruction chung:\n{settings.instructions}\n\n"
                f"Nhiệm vụ từ Orchestrator:\n{state.get('orchestrator_task', '')}\n"
                f"Hướng dẫn vai trò:\n{node.data.get('instructions', '')}\n"
                "Báo cáo kết quả và bằng chứng thực tế cho Orchestrator. Không tự commit/push."
                " Nếu cần thông tin hoặc xác nhận từ người tạo ticket, chỉ trả lời bắt đầu bằng "
                "@@ASK_USER: rồi ghi câu hỏi; hệ thống sẽ dừng chờ người tạo ticket trả lời."
                f"\nArtifacts mới nhất:\n{json.dumps(latest, ensure_ascii=False)}"
            )
            result = await make_node(assigned, agents)(state, config)
            text = result["outputs"][-1]["text"].strip()
            if text.startswith("@@ASK_USER:"):
                question = text.removeprefix("@@ASK_USER:").strip()
                if not question:
                    raise ValueError("Agent cần nêu câu hỏi cho người tạo ticket")
                result["orchestrator_question"] = question
                result["orchestrator_resume"] = node.id
                result["last_route"] = result.get("last_route", {}) | {node.id: "ASK_USER"}
            else:
                result["last_route"] = result.get("last_route", {}) | {node.id: "coordinator"}
            return result

        builder.add_node(nid, execute)
        builder.add_conditional_edges(
            nid,
            lambda state, key=nid: state["last_route"][key],
            {"ASK_USER": "orchestrator_input", "coordinator": "coordinator"},
        )
    return builder.compile(checkpointer=checkpointer)
