import type { Node, Edge, Viewport } from "@xyflow/react";
import { clientId } from "@/lib/client-id";
import type { components } from "@/lib/api/schema";
export type WorkflowGraph = components["schemas"]["Graph"];
export type NodeKind = NonNullable<WorkflowGraph["nodes"]>[number]["type"];
export type StepData = Record<string, unknown>;
export type FlowNode = Node<StepData, NodeKind>;
export type FlowEdge = Edge;
export type Snapshot = {
  nodes: FlowNode[];
  edges: FlowEdge[];
  viewport: Viewport;
};
export const defaultViewport = { x: 0, y: 0, zoom: 1 };
export function deserialize(graph: WorkflowGraph): Snapshot {
  return {
    nodes: (graph.nodes || []).map((node) => ({
      ...node,
      position: { x: node.position?.x || 0, y: node.position?.y || 0 },
      data: {
        ...node.data,
        ...(node.type === "git_release" &&
        (graph.edges || []).some(
          (e) =>
            e.source === node.id &&
            (!e.sourceHandle || e.sourceHandle === "default"),
        )
          ? { _legacyDefault: true }
          : {}),
      },
    })),
    edges: (graph.edges || []).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle || "default",
      type: "labeled",
    })),
    viewport: { ...defaultViewport, ...graph.viewport },
  };
}
export function serialize(state: Snapshot): WorkflowGraph {
  return {
    nodes: state.nodes.map(({ id, type, position, data }) => ({
      id,
      type: type!,
      position: { x: position.x, y: position.y },
      data: Object.fromEntries(
        Object.entries(data).filter(([key]) => !key.startsWith("_")),
      ),
    })),
    edges: state.edges.map(({ id, source, target, sourceHandle }) => ({
      id,
      source,
      target,
      sourceHandle:
        !sourceHandle || sourceHandle === "default" ? null : sourceHandle,
    })),
    viewport: { ...state.viewport },
  };
}
export function graphKey(state: Snapshot) {
  return JSON.stringify({ ...serialize(state), viewport: defaultViewport });
}
export const nodeId = () =>
  `n_${clientId().replaceAll("-", "").slice(0, 10)}`;
