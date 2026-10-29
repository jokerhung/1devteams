"""Build the persisted, versioned participant snapshot for canvas-free orchestration."""

from app.schemas.workflow import Edge, Graph, Node, OrchestratorConfig


def orchestrator_graph(config: OrchestratorConfig, agents) -> Graph:
    active = [agent for agent in agents if agent.is_active and agent.role_key != "WORKFLOW"]
    coordinator = next((agent for agent in active if agent.id == str(config.coordinator_agent_id)), None)
    if coordinator is None:
        raise ValueError("Agent điều phối phải đang hoạt động và thuộc project")
    workers = [agent for agent in active if agent.id != coordinator.id]
    if not workers:
        raise ValueError("Project cần ít nhất một agent thực hiện ngoài agent điều phối")
    nodes = [Node(id="start", type="start"), Node(id="end", type="end")]
    nodes.append(
        Node(
            id="coordinator",
            type="agent",
            data={
                "agent_id": coordinator.id,
                "label": coordinator.display_name,
                "instructions": config.instructions,
                "max_iterations": config.max_rounds,
            },
        )
    )
    edges = [
        Edge(id="start_coordinator", source="start", target="coordinator"),
        Edge(id="coordinator_end", source="coordinator", target="end"),
    ]
    for index, agent in enumerate(workers):
        nid = f"worker_{index}"
        nodes.append(
            Node(
                id=nid,
                type="agent",
                data={
                    "agent_id": agent.id,
                    "label": agent.display_name,
                    "agent_handle": agent.handle,
                    "instructions": "Làm nhiệm vụ từ điều phối; báo cáo kết quả, bằng chứng, lỗi.",
                    "max_iterations": config.max_rounds,
                },
            )
        )
        edges.append(Edge(id=f"{nid}_return", source=nid, target="coordinator"))
    return Graph(nodes=nodes, edges=edges, orchestrator=config)


def validate_orchestrator(graph: Graph, agents) -> list[str]:
    config = graph.orchestrator
    if config is None:
        return []
    errors = []
    by_id = {agent.id: agent for agent in agents if agent.is_active}
    coordinator = [node for node in graph.nodes if node.id == "coordinator" and node.type == "agent"]
    if len(coordinator) != 1 or str(coordinator[0].data.get("agent_id")) != str(config.coordinator_agent_id):
        errors.append("Orchestrator thiếu agent điều phối hợp lệ")
    if not config.instructions.strip():
        errors.append("Nhập instruction cho Orchestrator")
    ids = [node.id for node in graph.nodes]
    if len(ids) != len(set(ids)) or ids.count("start") != 1 or ids.count("end") != 1:
        errors.append("Cấu trúc Orchestrator không hợp lệ")
    if not any(n.id == "start" and n.type == "start" for n in graph.nodes) or not any(
        n.id == "end" and n.type == "end" for n in graph.nodes
    ):
        errors.append("Orchestrator cần start/end hợp lệ")
    workers = [node for node in graph.nodes if node.id.startswith("worker_") and node.type == "agent"]
    if not workers or len(graph.nodes) != len(workers) + 3:
        errors.append("Orchestrator cần agent thực hiện")
    participants = coordinator + workers
    if len({str(node.data.get("agent_id")) for node in participants}) != len(participants):
        errors.append("Agent điều phối và agent thực hiện phải khác nhau")
    for node in participants:
        agent = by_id.get(str(node.data.get("agent_id")))
        if agent is None:
            errors.append(f"{node.id}: agent không còn hoạt động trong project")
    return errors
