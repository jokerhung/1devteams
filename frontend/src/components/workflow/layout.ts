import dagre from "dagre";
import type { Snapshot } from "./serialize";
export function autoLayout(state: Snapshot): Snapshot {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });
  state.nodes.forEach((node) =>
    graph.setNode(node.id, { width: 250, height: 165 }),
  );
  state.edges.forEach((edge) => {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target))
      graph.setEdge(edge.source, edge.target);
  });
  dagre.layout(graph);
  return {
    ...state,
    nodes: state.nodes.map((node) => {
      const position = graph.node(node.id);
      return {
        ...node,
        position: { x: position.x - 125, y: position.y - 82.5 },
      };
    }),
  };
}
