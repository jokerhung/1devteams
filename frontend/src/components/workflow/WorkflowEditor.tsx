"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ReactFlowProvider, type ReactFlowInstance } from "@xyflow/react";
import { useStore } from "zustand";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import type { Agent, Project, Workflow, Team, Ticket, User } from "@/lib/types";
import { keys } from "@/lib/query-keys";
import {
  Loading,
  ErrorState,
  ConfirmDialog,
} from "@/components/ui-app/primitives";
import { AgentForm } from "@/components/ui-app/agent-form";
import { CreateTicketDialog } from "@/components/ui-app/ticket-dialog";
import { createWorkflowStore } from "./store";
import { graphKey, serialize, nodeId, type FlowNode } from "./serialize";
import { validateGraph, type ValidationIssue } from "./validate";
import { autoLayout } from "./layout";
import { loadTemplateGraph, type TemplateId } from "./templates";
import { WorkflowToolbar } from "./WorkflowToolbar";
import { SidebarPalette, type PaletteItem } from "./SidebarPalette";
import { WorkflowCanvas } from "./WorkflowCanvas";
import { NodeInspector } from "./NodeInspector";
import { ValidationPanel } from "./ValidationPanel";
import { PipelineView } from "./PipelineView";
type ValidationResult = {
  is_valid: boolean;
  errors: string[];
  current_version: number;
};
function backendIssues(errors: string[], nodes: FlowNode[]): ValidationIssue[] {
  return errors.map((message) => ({
    message,
    nodeId: nodes.find((n) => message.startsWith(`${n.id}:`))?.id,
  }));
}
export function WorkflowEditor({ pid, wid }: { pid: string; wid: string }) {
  const workflow = useQuery({
    queryKey: keys.workflow(wid),
    queryFn: () => apiFetch<Workflow>(`/workflows/${wid}`),
  });
  const project = useQuery({
    queryKey: keys.project(pid),
    queryFn: () => apiFetch<Project>(`/projects/${pid}`),
  });
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  if (workflow.isLoading || project.isLoading || agents.isLoading)
    return <Loading />;
  if (!workflow.data || !project.data || !agents.data)
    return (
      <ErrorState error={workflow.error || project.error || agents.error} />
    );
  if (workflow.data.project_id !== pid)
    return <ErrorState error={new Error("Workflow không thuộc project này")} />;
  return (
    <ReactFlowProvider>
      <Editor
        key={wid}
        initial={workflow.data}
        project={project.data}
        agents={agents.data}
      />
    </ReactFlowProvider>
  );
}
function Editor({
  initial,
  project,
  agents,
}: {
  initial: Workflow;
  project: Project;
  agents: Agent[];
}) {
  const client = useQueryClient();
  const [store] = useState(() => createWorkflowStore(initial.graph));
  const state = useStore(store),
    history = useStore(store.temporal);
  const [workflow, setWorkflow] = useState(initial);
  const key = graphKey(state),
    dirty = key !== state.savedKey;
  const [view, setView] = useState<"canvas" | "pipeline">("canvas");
  const [busy, setBusy] = useState(false),
    [publishOpen, setPublishOpen] = useState(false),
    [ticketOpen, setTicketOpen] = useState(false);
  const [firstPublish, setFirstPublish] = useState(false),
    [lastSaved, setLastSaved] = useState(initial.updated_at);
  const [editAgent, setEditAgent] = useState<Agent | null>(null);
  const [clientIssues, setClientIssues] = useState(() =>
    validateGraph(serialize(state), agents),
  );
  const [serverValidation, setServerValidation] = useState<{
    key: string;
    issues: ValidationIssue[];
  } | null>(null);
  const rf = useRef<ReactFlowInstance<FlowNode> | null>(null);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  const archived = workflow.status === "ARCHIVED";
  const issues =
    serverValidation?.key === key ? serverValidation.issues : clientIssues;
  const teams = useQuery({
    queryKey: keys.teams,
    queryFn: () => apiFetch<Team[]>("/teams"),
    enabled: !!editAgent,
  });
  const me = useQuery({
    queryKey: keys.me,
    queryFn: () => apiFetch<User>("/auth/me"),
  });
  const tickets = useQuery({
    queryKey: keys.tickets(workflow.id),
    queryFn: () => apiFetch<Ticket[]>(`/workflows/${workflow.id}/tickets`),
    enabled: publishOpen,
  });
  useEffect(() => {
    setServerValidation(null);
    const timer = setTimeout(
      () => setClientIssues(validateGraph(serialize(store.getState()), agents)),
      300,
    );
    return () => clearTimeout(timer);
  }, [key, agents, store]);
  // A synchronous check prevents publishing during the validation debounce window.
  const valid =
    !issues.length && !validateGraph(serialize(state), agents).length;
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) e.preventDefault();
    };
    const click = (e: MouseEvent) => {
      if (
        !dirtyRef.current ||
        e.defaultPrevented ||
        e.ctrlKey ||
        e.metaKey ||
        e.shiftKey ||
        e.altKey ||
        e.button !== 0
      )
        return;
      const anchor = (e.target as Element).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      const logout = (e.target as Element).closest?.(
        'button[aria-label="Đăng xuất"]',
      );
      if (
        (logout ||
          (anchor &&
            anchor.target !== "_blank" &&
            new URL(anchor.href).pathname !== location.pathname)) &&
        !window.confirm("Có thay đổi chưa lưu. Bạn có muốn rời trang?")
      ) {
        e.preventDefault();
        e.stopPropagation();
      }
    };
    const pop = (e: PopStateEvent) => {
      if (
        dirtyRef.current &&
        !window.confirm("Có thay đổi chưa lưu. Bạn có muốn rời trang?")
      ) {
        e.stopImmediatePropagation();
        window.history.forward();
      }
    };
    window.addEventListener("beforeunload", before);
    document.addEventListener("click", click, true);
    window.addEventListener("popstate", pop, true);
    return () => {
      window.removeEventListener("beforeunload", before);
      document.removeEventListener("click", click, true);
      window.removeEventListener("popstate", pop, true);
    };
  }, []);
  const invalidate = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["projects"] }),
      client.invalidateQueries({ queryKey: keys.workflow(workflow.id) }),
    ]);
  };
  const save = useCallback(async () => {
    if (busy || archived) return;
    const snapshot = store.getState(),
      savedKey = graphKey(snapshot);
    setBusy(true);
    try {
      const result = await send<ValidationResult>(
        `/workflows/${workflow.id}/graph`,
        serialize(snapshot),
        "PUT",
      );
      store.setState({ savedKey });
      setServerValidation({
        key: savedKey,
        issues: backendIssues(result.errors, snapshot.nodes),
      });
      setWorkflow((w) => ({
        ...w,
        current_version: result.current_version,
        is_valid: result.is_valid,
        validation_errors: result.errors,
      }));
      setLastSaved(new Date().toISOString());
      await Promise.all([
        client.invalidateQueries({ queryKey: ["projects"] }),
        client.invalidateQueries({ queryKey: keys.workflow(workflow.id) }),
      ]);
      toast.success(
        result.is_valid
          ? "Đã lưu workflow hợp lệ"
          : "Đã lưu nháp. Sửa lỗi trước khi xuất bản.",
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [archived, busy, client, store, workflow.id]);
  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      const element = event.target as HTMLElement;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
        return;
      }
      if (
        element.closest(
          "input,textarea,select,[contenteditable=true],[role=dialog]",
        )
      )
        return;
      if (busy || archived) return;
      if (
        (event.ctrlKey || event.metaKey) &&
        ["z", "y", "d"].includes(event.key.toLowerCase())
      ) {
        event.preventDefault();
        const key = event.key.toLowerCase();
        if (key === "d") store.getState().duplicateSelected();
        else if (key === "y" || event.shiftKey)
          store.temporal.getState().redo();
        else store.temporal.getState().undo();
      } else if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        store.getState().removeSelected();
      }
    };
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [save, store, busy, archived]);
  const add = (item: PaletteItem, position?: { x: number; y: number }) => {
    if (busy || archived) return;
    const agent = agents.find((a) => a.id === item.agent_id);
    const type = agent?.permission_profile.can_git_release
      ? "git_release"
      : item.type;
    const data =
      type === "agent"
        ? {
            agent_id: agent?.id || null,
            routing:
              agent?.role_key === "BA"
                ? "ba"
                : agent?.role_key === "TESTER"
                  ? "tester"
                  : "none",
          }
        : type === "git_release"
          ? { agent_id: agent?.id || null, push: true }
          : type === "human_confirm"
            ? {
                message: "Bạn xác nhận lỗi đã được sửa xong?",
                approved_label: "Đồng ý",
                rejected_label: "Từ chối",
              }
            : type === "condition"
              ? { expression: "len(modified_files) > 0" }
              : {};
    const canvas = document
      .querySelector('[data-testid="workflow-canvas"]')
      ?.getBoundingClientRect();
    const center =
      canvas && rf.current
        ? rf.current.screenToFlowPosition({
            x: canvas.left + canvas.width / 2,
            y: canvas.top + canvas.height / 2,
          })
        : { x: 100, y: 100 };
    store
      .getState()
      .addNode({ id: nodeId(), type, data, position: position || center });
  };
  const focus = (id: string) => {
    setView("canvas");
    store.getState().select(id);
    setTimeout(() => {
      const n = store.getState().nodes.find((n) => n.id === id);
      if (n)
        rf.current?.setCenter(n.position.x + 125, n.position.y + 80, {
          zoom: 1,
          duration: 250,
        });
    }, 50);
  };
  const loadTemplate = async (template: TemplateId) => {
    if (
      dirty &&
      !confirm(
        "Thay toàn bộ canvas bằng mẫu? Các thay đổi chưa lưu sẽ bị thay thế.",
      )
    )
      return;
    try {
      store.getState().replace(await loadTemplateGraph(template, project.id));
    } catch (error) {
      toast.error((error as Error).message);
      return;
    }
    setView("canvas");
    setTimeout(() => rf.current?.fitView({ padding: 0.15 }), 50);
  };
  return (
    <div
      className="-mx-3 -my-2 flex h-[calc(100dvh-80px)] min-h-[650px] flex-col overflow-hidden rounded-xl border border-stone-200 bg-white"
      data-testid="workflow-editor"
    >
      <WorkflowToolbar
        workflow={workflow}
        project={project}
        dirty={dirty}
        valid={valid}
        busy={busy}
        archived={archived}
        view={view}
        lastSaved={lastSaved}
        canUndo={!!history.pastStates.length}
        canRedo={!!history.futureStates.length}
        onUndo={() => history.undo()}
        onRedo={() => history.redo()}
        onSave={() => void save()}
        onValidate={async () => {
          setBusy(true);
          try {
            const snapshot = store.getState();
            const result = await send<ValidationResult>(
              `/workflows/${workflow.id}/validate`,
              serialize(snapshot),
            );
            setServerValidation({
              key: graphKey(snapshot),
              issues: backendIssues(result.errors, snapshot.nodes),
            });
          } catch (e) {
            toast.error((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
        onPublish={() => setPublishOpen(true)}
        onLayout={() => {
          const laidOut = autoLayout(store.getState());
          store.setState(laidOut);
          setTimeout(() => rf.current?.fitView({ padding: 0.15 }), 50);
        }}
        onTemplate={loadTemplate}
        onView={setView}
      />
      {firstPublish && (
        <div className="flex items-center justify-between bg-emerald-50 px-4 py-2 text-xs text-emerald-800">
          Đã xuất bản workflow. Bạn có thể tạo ticket đầu tiên.
          <button className="btn btn-dark" onClick={() => setTicketOpen(true)}>
            Tạo ticket đầu tiên
          </button>
        </div>
      )}
      <div className="flex min-h-0 flex-1 overflow-x-auto">
        {view === "canvas" ? (
          <>
            <SidebarPalette
              agents={agents}
              onAdd={add}
              disabled={archived || busy}
            />
            <WorkflowCanvas
              store={store}
              agents={agents}
              issues={issues}
              branch={`${project.git_remote} / ${project.default_branch}`}
              disabled={archived || busy}
              onDrop={add}
              onInit={(instance) => {
                rf.current = instance;
                if (
                  initial.graph.viewport?.zoom === 1 &&
                  initial.graph.viewport?.x === 0 &&
                  initial.graph.viewport?.y === 0
                )
                  void instance.fitView({ padding: 0.15 });
              }}
            />
            <NodeInspector
              node={state.nodes.find((n) => n.selected)}
              nodes={state.nodes}
              agents={agents}
              disabled={archived || busy}
              onChange={(data) => {
                const selected = store.getState().nodes.find((n) => n.selected);
                if (selected) store.getState().updateNode(selected.id, data);
              }}
              onDelete={() => store.getState().removeSelected()}
              onEditAgent={(agent) => {
                if (["OWNER", "ADMIN"].includes(me.data?.system_role || ""))
                  setEditAgent(agent);
                else toast.error("Chỉ quản trị viên được sửa cấu hình agent");
              }}
            />
          </>
        ) : (
          <div className="min-w-0 flex-1">
            <PipelineView
              graph={serialize(state)}
              agents={agents}
              workspacePath={project.workspace_path}
            />
          </div>
        )}
      </div>
      <ValidationPanel issues={issues} onFocus={focus} />
      {publishOpen && (
        <ConfirmDialog
          title="Xuất bản workflow"
          onClose={() => setPublishOpen(false)}
          onConfirm={async () => {
            if (dirty || !valid)
              throw new Error("Lưu workflow hợp lệ trước khi xuất bản");
            const published = await send<Workflow>(
              `/workflows/${workflow.id}/publish`,
            );
            setFirstPublish(!workflow.published_version);
            setWorkflow(published);
            setPublishOpen(false);
            await invalidate();
            toast.success(`Đã xuất bản v${published.published_version}`);
          }}
        >
          <p>
            Ticket mới của workflow này sẽ dùng phiên bản v
            {workflow.current_version}.{" "}
            {tickets.data?.filter((t) =>
              [
                "RUNNING",
                "WAITING_USER_INPUT",
                "WAITING_USER_CONFIRM",
              ].includes(t.status),
            ).length ?? "…"}{" "}
            ticket đang chạy vẫn dùng phiên bản cũ.
          </p>
        </ConfirmDialog>
      )}
      {editAgent && teams.data && (
        <AgentForm
          agent={editAgent}
          teams={teams.data}
          onClose={() => {
            setEditAgent(null);
            void client.invalidateQueries({
              queryKey: keys.effective(project.id),
            });
          }}
          onRestart={() => {}}
        />
      )}
      {ticketOpen && (
        <CreateTicketDialog
          pid={project.id}
          wid={workflow.id}
          onClose={() => setTicketOpen(false)}
        />
      )}
    </div>
  );
}
