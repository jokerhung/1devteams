"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ReactFlowProvider, type ReactFlowInstance } from "@xyflow/react";
import { useStore } from "zustand";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { send } from "@/lib/api";
import type { Agent } from "@/lib/types";
import { createWorkflowStore } from "./store";
import {
  graphKey,
  serialize,
  nodeId,
  type WorkflowGraph,
  type FlowNode,
} from "./serialize";
import { autoLayout } from "./layout";
import { validateGraph } from "./validate";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { SidebarPalette, type PaletteItem } from "./SidebarPalette";
import { NodeInspector } from "./NodeInspector";
import { ValidationPanel } from "./ValidationPanel";
import { PipelineView } from "./PipelineView";

type Props = {
  template: { id: string; name: string; graph: WorkflowGraph };
  agents: Agent[];
  editable: boolean;
};
export function TemplateEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <Editor {...props} />
    </ReactFlowProvider>
  );
}
function Editor({ template, agents, editable }: Props) {
  const client = useQueryClient();
  const [store] = useState(() => createWorkflowStore(template.graph));
  const state = useStore(store),
    history = useStore(store.temporal);
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<"canvas" | "pipeline">("canvas");
  const rf = useRef<ReactFlowInstance<FlowNode> | null>(null);
  const dirty = graphKey(state) !== state.savedKey;
  const disabled = !editable || busy;
  const issues = validateGraph(serialize(state), agents);
  useEffect(() => {
    if (!dirty) return;
    const unload = (e: BeforeUnloadEvent) => e.preventDefault();
    const leave = (e: MouseEvent) => {
      const link = (e.target as Element).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        link &&
        link.pathname !== location.pathname &&
        !window.confirm("Có thay đổi chưa lưu. Bạn có muốn rời trang?")
      ) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", leave, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", leave, true);
    };
  }, [dirty]);
  const add = (item: PaletteItem, point?: { x: number; y: number }) => {
    if (disabled) return;
    const agent = agents.find((a) => a.id === item.agent_id);
    const type = agent?.permission_profile.can_git_release
      ? "git_release"
      : item.type;
    store.getState().addNode({
      id: nodeId(),
      type,
      position: point || { x: 200, y: 180 },
      data: {
        ...(agent
          ? {
              agent_id: agent.id,
              routing:
                agent.role_key === "BA"
                  ? "ba"
                  : agent.role_key === "TESTER"
                    ? "tester"
                    : "none",
              requires_write: agent.permission_profile.allow_write,
            }
          : {}),
        ...(type === "condition"
          ? { expression: "len(modified_files) > 0" }
          : {}),
      },
    });
  };
  const save = async () => {
    if (disabled || issues.length) return;
    const snapshot = store.getState(),
      savedKey = graphKey(snapshot);
    setBusy(true);
    try {
      await send(
        `/workflow-templates/${template.id}`,
        { graph: serialize(snapshot) },
        "PUT",
      );
      store.setState({ savedKey });
      await client.invalidateQueries({ queryKey: ["workflow-templates"] });
      toast.success("Đã lưu template");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (disabled) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === "s") {
        event.preventDefault();
        void save();
        return;
      }
      if (
        (event.target as HTMLElement).closest(
          "input,textarea,select,[contenteditable=true]",
        )
      )
        return;
      if ((event.ctrlKey || event.metaKey) && ["z", "y", "d"].includes(key)) {
        event.preventDefault();
        if (key === "d") store.getState().duplicateSelected();
        else if (key === "y" || event.shiftKey) history.redo();
        else history.undo();
      } else if (["Delete", "Backspace"].includes(event.key)) {
        event.preventDefault();
        store.getState().removeSelected();
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  });
  return (
    <div
      className="-mx-3 -my-2 flex h-[calc(100dvh-80px)] min-h-[650px] flex-col overflow-hidden rounded-xl border border-stone-200 bg-white"
      data-testid="template-editor"
    >
      <header className="space-y-3 border-b border-stone-200 p-3">
        <div className="flex items-center gap-2 text-sm">
          <Link className="text-stone-500 hover:underline" href="/templates">
            Template
          </Link>
          <span>/</span>
          <h1 className="font-semibold">{template.name}</h1>
          <span className="badge">{editable ? "Chỉnh sửa" : "Chỉ xem"}</span>
          {dirty && <span className="text-xs text-amber-700">Chưa lưu</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="btn btn-light"
            disabled={disabled || !history.pastStates.length}
            onClick={() => history.undo()}
          >
            Hoàn tác
          </button>
          <button
            className="btn btn-light"
            disabled={disabled || !history.futureStates.length}
            onClick={() => history.redo()}
          >
            Làm lại
          </button>
          <button
            className="btn btn-light"
            disabled={disabled}
            onClick={() => {
              store.setState(autoLayout(store.getState()));
              setTimeout(() => rf.current?.fitView({ padding: 0.15 }), 50);
            }}
          >
            Tự sắp xếp
          </button>
          <button
            className="btn btn-light"
            onClick={() => setView(view === "canvas" ? "pipeline" : "canvas")}
          >
            {view === "canvas" ? "Pipeline" : "Canvas"}
          </button>
          {editable ? (
            <button
              className="btn btn-dark"
              disabled={busy || !dirty || !!issues.length}
              onClick={() => void save()}
            >
              {busy ? "Đang lưu…" : "Lưu template"}
            </button>
          ) : (
            <Link
              className="btn btn-dark"
              href={`/templates/${template.id}?edit=1`}
            >
              Sửa template
            </Link>
          )}
        </div>
        <p className="text-xs text-stone-500">
          Thay đổi được áp dụng khi tạo workflow mới từ mẫu. Workflow hiện có
          giữ nguyên.
        </p>
      </header>
      <div className="flex min-h-0 flex-1 overflow-x-auto">
        {view === "canvas" ? (
          <>
            <SidebarPalette
              agentLabel="Agent cho template"
              agents={agents}
              onAdd={add}
              disabled={disabled}
            />
            <WorkflowCanvas
              store={store}
              agents={agents}
              issues={issues}
              branch="Template"
              disabled={disabled}
              onDrop={add}
              onInit={(instance) => {
                rf.current = instance;
                void instance.fitView({ padding: 0.15 });
              }}
            />
            <NodeInspector
              node={state.nodes.find((n) => n.selected)}
              nodes={state.nodes}
              agents={agents}
              disabled={disabled}
              onChange={(data) => {
                const selected = store.getState().nodes.find((n) => n.selected);
                if (selected) store.getState().updateNode(selected.id, data);
              }}
              onDelete={() => store.getState().removeSelected()}
              onEditAgent={() =>
                toast.info("Sửa cấu hình agent tại Agents & Teams")
              }
            />
          </>
        ) : (
          <div className="min-w-0 flex-1">
            <PipelineView
              graph={serialize(state)}
              agents={agents}
              workspacePath="Theo project áp dụng template"
            />
          </div>
        )}
      </div>
      <ValidationPanel
        issues={issues}
        onFocus={(id) => {
          setView("canvas");
          store.getState().select(id);
        }}
      />
    </div>
  );
}
