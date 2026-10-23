from collections import defaultdict, deque

from app.db.models import Agent
from app.schemas.workflow import Graph


def reachable(start: str, links: dict[str, list[str]], skip: set[str] | None = None) -> set[str]:
    seen: set[str] = set()
    pending = [start]
    while pending:
        item = pending.pop()
        if item in seen or (skip and item in skip):
            continue
        seen.add(item)
        pending.extend(links.get(item, []))
    return seen


def validate_graph(graph: Graph, agents: list[Agent]) -> list[str]:
    errors = []
    nodes = {node.id: node for node in graph.nodes}
    if len(nodes) != len(graph.nodes):
        errors.append("ID node bị trùng")
    if len({edge.id for edge in graph.edges}) != len(graph.edges):
        errors.append("ID cạnh bị trùng")
    starts = [node.id for node in graph.nodes if node.type == "start"]
    ends = [node.id for node in graph.nodes if node.type == "end"]
    if len(starts) != 1 or not ends:
        errors.append("Workflow cần đúng 1 start và ít nhất 1 end")
    forward, backward, unsafe = defaultdict(list), defaultdict(list), defaultdict(list)
    handles = defaultdict(list)
    for edge in graph.edges:
        if edge.source not in nodes or edge.target not in nodes:
            errors.append("Cạnh tham chiếu node không tồn tại")
            continue
        forward[edge.source].append(edge.target)
        backward[edge.target].append(edge.source)
        handles[edge.source].append(None if edge.sourceHandle == "default" else edge.sourceHandle)
        if not (nodes[edge.source].type == "human_confirm" and edge.sourceHandle == "approved"):
            unsafe[edge.source].append(edge.target)
    if len(starts) == 1:
        reached = reachable(starts[0], forward)
        to_end = set().union(*(reachable(end, backward) for end in ends)) if ends else set()
        if set(nodes) - reached:
            errors.append("Mọi node phải đi tới được từ start")
        if set(nodes) - to_end:
            errors.append("Mọi node phải có đường tới end")
    by_id = {agent.id: agent for agent in agents if agent.is_active}
    for node in graph.nodes:
        iterations = node.data.get("max_iterations")
        if iterations is not None and (type(iterations) is not int or not 1 <= iterations <= 1000):
            errors.append(f"{node.id}: max_iterations phải là số nguyên từ 1 đến 1000")
        routing = node.data.get("routing", "none")
        required: set[str | None] = {None}
        if node.type == "end":
            required = set()
        elif node.type == "human_confirm":
            required = {"approved", "rejected"}
        elif node.type == "condition":
            required = {"true", "false"}
            if not isinstance(node.data.get("expression"), str) or not node.data["expression"].strip():
                errors.append(f"{node.id}: condition cần expression")
            else:
                from app.engine.conditions import evaluate

                try:
                    evaluate(node.data["expression"], {})
                except ValueError:
                    errors.append(f"{node.id}: expression không hợp lệ")
        elif node.type == "agent":
            if routing == "ba":
                required = {"need_info", "ready"}
            elif routing in {"tester", "review"}:
                required = {"pass", "fail"}
            elif routing != "none":
                errors.append(f"{node.id}: routing không hợp lệ")
        elif node.type == "git_release":
            required = set() if not handles[node.id] else {None}
            if set(handles[node.id]) <= {"success", "failed"} and handles[node.id]:
                required = {"success"}
        actual = handles[node.id]
        permitted = required | ({"failed"} if node.type == "git_release" else set())
        if required - set(actual) or set(actual) - permitted or len(actual) != len(set(actual)):
            errors.append(f"{node.id}: thiếu nhánh hoặc handle không hợp lệ")
        if node.type == "end" and actual:
            errors.append(f"{node.id}: end không có cạnh ra")
        if node.type in {"agent", "git_release"}:
            agent = by_id.get(str(node.data.get("agent_id")))
            if agent is None:
                errors.append(f"{node.id}: agent phải thuộc project và đang hoạt động")
                continue
            needs_write = node.data.get("requires_write") or agent.role_key == "DEVELOPER"
            needs_terminal = routing == "tester" or node.data.get("requires_terminal")
            if agent.runtime == "openai-api" and (
                node.type == "git_release" or needs_write or needs_terminal
            ):
                errors.append(
                    f"{agent.handle} dùng OpenAI Custom chỉ trả lời văn bản, "
                    "không thể sửa file / chạy test / phát hành Git"
                )
            if needs_write and not agent.permission_profile.get("allow_write"):
                errors.append(f"{node.id}: node sửa file cần quyền ghi")
            if needs_terminal and not agent.permission_profile.get("allow_terminal"):
                errors.append(f"{node.id}: tester cần quyền chạy terminal")
            if node.type == "git_release":
                if not agent.permission_profile.get("can_git_release"):
                    errors.append(f"{node.id}: agent không có quyền phát hành Git")
                if len(starts) == 1 and node.id in reachable(starts[0], unsafe):
                    errors.append(f"{node.id}: mọi đường phát hành Git phải qua human_confirm nhánh approved")
    # Remove agent nodes, then Kahn's algorithm: any remaining cycle is an empty loop.
    non_agents = {key for key, node in nodes.items() if node.type == "agent"}
    remaining = set(nodes) - non_agents
    degrees = {key: sum(source in remaining for source in backward[key]) for key in remaining}
    queue = deque(key for key, degree in degrees.items() if degree == 0)
    processed = 0
    while queue:
        key = queue.popleft()
        processed += 1
        for target in forward[key]:
            if target in degrees:
                degrees[target] -= 1
                if degrees[target] == 0:
                    queue.append(target)
    if processed != len(remaining):
        errors.append("Mỗi chu trình phải có ít nhất 1 agent node")
    return list(dict.fromkeys(errors))
