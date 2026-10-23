"use client";
import { useRef } from "react";
import { useStore } from "zustand";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  MarkerType,
  type ReactFlowInstance,
} from "@xyflow/react";
import type { Agent } from "@/lib/types";
import type { WorkflowStore } from "./store";
import { validConnection } from "./store";
import { BaseNode } from "./nodes/BaseNode";
import { LabeledEdge } from "./edges/LabeledEdge";
import type { FlowNode, Snapshot } from "./serialize";
import type { ValidationIssue } from "./validate";
import type { PaletteItem } from "./SidebarPalette";
import "@xyflow/react/dist/style.css";
export const nodeTypes = {
  start: BaseNode,
  agent: BaseNode,
  condition: BaseNode,
  human_input: BaseNode,
  human_confirm: BaseNode,
  git_release: BaseNode,
  end: BaseNode,
};
export const edgeTypes = { labeled: LabeledEdge };
export function WorkflowCanvas({
  store,
  agents,
  issues,
  branch,
  disabled,
  onDrop,
  onInit,
}: {
  store: WorkflowStore;
  agents: Agent[];
  issues: ValidationIssue[];
  branch: string;
  disabled?: boolean;
  onDrop: (item: PaletteItem, point: { x: number; y: number }) => void;
  onInit: (instance: ReactFlowInstance<FlowNode>) => void;
}) {
  const nodes = useStore(store, (s) => s.nodes),
    edges = useStore(store, (s) => s.edges);
  const instance = useRef<ReactFlowInstance<FlowNode>>(null);
  const dragStart = useRef<Snapshot | null>(null);
  const rendered = nodes.map((n) => ({
    ...n,
    data: {
      ...n.data,
      _agent: agents.find((a) => a.id === n.data.agent_id),
      _errors: issues.filter((i) => i.nodeId === n.id).map((i) => i.message),
      _branch: branch,
    },
  }));
  return (
    <div
      data-testid="workflow-canvas"
      className="min-h-0 min-w-0 flex-1"
      onDragOver={(e) => {
        if (!disabled) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "move";
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        if (disabled || !instance.current) return;
        try {
          const item = JSON.parse(
            e.dataTransfer.getData("application/aiteams-node"),
          ) as PaletteItem;
          if (!(item.type in nodeTypes)) return;
          onDrop(
            item,
            instance.current.screenToFlowPosition({
              x: e.clientX,
              y: e.clientY,
            }),
          );
        } catch {
          /* Ignore unrelated browser drags. */
        }
      }}
    >
      <ReactFlow<FlowNode>
        nodes={rendered}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        defaultViewport={store.getState().viewport}
        defaultEdgeOptions={{
          type: "labeled",
          markerEnd: { type: MarkerType.ArrowClosed },
        }}
        onInit={(rf) => {
          instance.current = rf;
          onInit(rf);
        }}
        onNodesChange={disabled ? undefined : store.getState().nodesChanged}
        onEdgesChange={disabled ? undefined : store.getState().edgesChanged}
        onConnect={store.getState().connect}
        isValidConnection={(connection) =>
          !disabled && validConnection(connection, store.getState())
        }
        nodesDraggable={!disabled}
        nodesConnectable={!disabled}
        edgesReconnectable={false}
        deleteKeyCode={null}
        minZoom={0.15}
        maxZoom={2}
        onMoveEnd={(_, viewport) => store.setState({ viewport })}
        onNodeDragStart={() => {
          dragStart.current = {
            nodes: store.getState().nodes,
            edges: store.getState().edges,
            viewport: store.getState().viewport,
          };
          store.temporal.getState().pause();
        }}
        onNodeDragStop={() => {
          const end = {
            nodes: store.getState().nodes,
            edges: store.getState().edges,
            viewport: store.getState().viewport,
          };
          if (dragStart.current) store.setState(dragStart.current);
          store.temporal.getState().resume();
          store.setState(end);
          dragStart.current = null;
        }}
        fitView={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1.5}
          color="#E7E5DA"
        />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) => (node.type === "agent" ? "#d6d3d1" : "#c7d2fe")}
        />
      </ReactFlow>
    </div>
  );
}
