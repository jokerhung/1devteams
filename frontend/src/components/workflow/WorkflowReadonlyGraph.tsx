"use client";
import {
  ReactFlow,
  Background,
  Controls,
  ReactFlowProvider,
} from "@xyflow/react";
import type { Agent } from "@/lib/types";
import { deserialize, type WorkflowGraph } from "./serialize";
import { nodeTypes, edgeTypes } from "./WorkflowCanvas";
export type WorkflowNodeStatus =
  "idle" | "running" | "done" | "waiting" | "failed";
export function WorkflowReadonlyGraph({
  graph,
  agents = [],
  nodeStatuses = {},
}: {
  graph: WorkflowGraph;
  agents?: Agent[];
  nodeStatuses?: Record<string, WorkflowNodeStatus>;
}) {
  const state = deserialize(graph);
  return (
    <div className="h-[480px] min-h-64" aria-label="Sơ đồ workflow chỉ đọc">
      <ReactFlowProvider>
        <ReactFlow
          nodes={state.nodes.map((n) => ({
            ...n,
            data: {
              ...n.data,
              _agent: agents.find((a) => a.id === n.data.agent_id),
              _status: nodeStatuses[n.id] || "idle",
            },
          }))}
          edges={state.edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          minZoom={0.1}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          edgesFocusable={false}
          nodesFocusable={false}
          deleteKeyCode={null}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#E7E5DA" />
          <Controls showInteractive={false} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
