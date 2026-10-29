from typing import Any

from langgraph.graph import END, START, StateGraph

from app.acp.types import AgentRuntimeConfig
from app.engine.conditions import evaluate
from app.engine.nodes import make_node
from app.engine.state import WorkflowState
from app.schemas.workflow import Graph
from app.services.workflow_validator import validate_graph


def compile_workflow(graph: Graph, agents: dict[str, AgentRuntimeConfig], checkpointer: Any) -> Any:
    from types import SimpleNamespace

    records = [
        SimpleNamespace(
            id=a.agent_id,
            is_active=True,
            runtime=a.runtime,
            handle=a.handle,
            role_key="CUSTOM",
            permission_profile=a.permission_profile.model_dump(),
        )
        for a in agents.values()
    ]
    errors = validate_graph(graph, records)  # type: ignore[arg-type]
    for node in graph.nodes:
        if node.type == "condition":
            evaluate(str(node.data.get("expression", "")), {})
    if errors:
        raise ValueError("; ".join(errors))
    if graph.orchestrator:
        from app.engine.orchestrator import compile_orchestrator

        return compile_orchestrator(graph, agents, checkpointer)
    sg = StateGraph(WorkflowState)
    for node in graph.nodes:
        sg.add_node(node.id, make_node(node, agents))
    start = next(n for n in graph.nodes if n.type == "start")
    sg.add_edge(START, start.id)
    for node in graph.nodes:
        outs = [e for e in graph.edges if e.source == node.id]
        if node.type == "end":
            sg.add_edge(node.id, END)
        elif len(outs) == 1 and outs[0].sourceHandle in {None, "default"}:
            sg.add_edge(node.id, outs[0].target)
        elif outs:

            def choose(state: WorkflowState, src: str = node.id) -> str:
                return state["last_route"][src]

            sg.add_conditional_edges(node.id, choose, {str(e.sourceHandle): e.target for e in outs})
        else:
            sg.add_edge(node.id, END)
    return sg.compile(checkpointer=checkpointer)
