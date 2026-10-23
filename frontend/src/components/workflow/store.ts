import { createStore } from "zustand/vanilla";
import { temporal } from "zundo";
import {
  applyNodeChanges,
  applyEdgeChanges,
  type NodeChange,
  type EdgeChange,
  type Connection,
} from "@xyflow/react";
import {
  deserialize,
  graphKey,
  nodeId,
  type Snapshot,
  type WorkflowGraph,
  type FlowNode,
} from "./serialize";
export function validConnection(
  connection: Pick<Connection, "source" | "target"> & {
    sourceHandle?: string | null;
  },
  state: Snapshot,
) {
  const source = state.nodes.find((n) => n.id === connection.source),
    target = state.nodes.find((n) => n.id === connection.target);
  return (
    !!source &&
    !!target &&
    source.type !== "end" &&
    target.type !== "start" &&
    source.id !== target.id &&
    !state.edges.some(
      (e) =>
        e.source === source.id &&
        (e.sourceHandle || "default") ===
          (connection.sourceHandle || "default"),
    )
  );
}
type EditorState = Snapshot & {
  savedKey: string;
  select: (id: string | null) => void;
  nodesChanged: (changes: NodeChange<FlowNode>[]) => void;
  edgesChanged: (changes: EdgeChange[]) => void;
  connect: (connection: Connection) => void;
  updateNode: (id: string, data: Record<string, unknown>) => void;
  addNode: (node: FlowNode) => void;
  removeSelected: () => void;
  duplicateSelected: () => void;
  replace: (graph: WorkflowGraph) => void;
};
export function createWorkflowStore(graph: WorkflowGraph) {
  const initial = deserialize(graph);
  return createStore<EditorState>()(
    temporal(
      (set, get) => ({
        ...initial,
        savedKey: graphKey(initial),
        select: (id) =>
          set((s) => ({
            nodes: s.nodes.map((n) => ({ ...n, selected: n.id === id })),
            edges: s.edges.map((e) => ({ ...e, selected: false })),
          })),
        nodesChanged: (changes) =>
          set((s) => ({ nodes: applyNodeChanges(changes, s.nodes) })),
        edgesChanged: (changes) =>
          set((s) => ({ edges: applyEdgeChanges(changes, s.edges) })),
        connect: (connection) => {
          if (validConnection(connection, get()))
            set((s) => ({
              edges: [
                ...s.edges,
                { ...connection, id: `e_${nodeId()}`, type: "labeled" },
              ],
            }));
        },
        updateNode: (id, data) =>
          set((s) => ({
            nodes: s.nodes.map((n) =>
              n.id === id ? { ...n, data: { ...n.data, ...data } } : n,
            ),
          })),
        addNode: (node) =>
          set((s) => ({
            nodes: [
              ...s.nodes.map((n) => ({ ...n, selected: false })),
              { ...node, selected: true },
            ],
          })),
        removeSelected: () =>
          set((s) => {
            const removed = new Set(
              s.nodes.filter((n) => n.selected).map((n) => n.id),
            );
            return {
              nodes: s.nodes.filter((n) => !removed.has(n.id)),
              edges: s.edges.filter(
                (e) =>
                  !e.selected &&
                  !removed.has(e.source) &&
                  !removed.has(e.target),
              ),
            };
          }),
        duplicateSelected: () =>
          set((s) => ({
            nodes: [
              ...s.nodes.map((n) => ({ ...n, selected: false })),
              ...s.nodes
                .filter((n) => n.selected)
                .map((n) => ({
                  ...n,
                  id: nodeId(),
                  position: { x: n.position.x + 50, y: n.position.y + 50 },
                  data: { ...n.data },
                  selected: true,
                })),
            ],
          })),
        replace: (next) => set(deserialize(next)),
      }),
      {
        limit: 100,
        partialize: ({ nodes, edges, viewport }) => ({
          nodes,
          edges,
          viewport,
        }),
        equality: (past, current) => graphKey(past) === graphKey(current),
      },
    ),
  );
}
export type WorkflowStore = ReturnType<typeof createWorkflowStore>;
