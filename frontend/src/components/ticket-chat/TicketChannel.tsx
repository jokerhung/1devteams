"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useStore } from "zustand";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { clientId } from "@/lib/client-id";
import { loadTicketHistory, type HistoryPage } from "@/lib/ticket-history";
import type {
  Agent,
  Members,
  Project,
  Ticket,
  Workflow,
  User,
} from "@/lib/types";
import { Loading, ErrorState } from "@/components/ui-app/primitives";
import { createTicketStore } from "@/stores/ticket-store";
import { useChatPrefs } from "@/stores/chat-prefs";
import { TicketSocket } from "@/lib/ws";
import type { WorkflowGraph } from "@/components/workflow/serialize";
import type {
  Attachment,
  ChatEvent,
  RuntimeState,
  PendingMessage,
} from "./types";
import { ChannelHeader } from "./ChannelHeader";
import { MessageStream } from "./MessageStream";
import { Composer } from "./Composer";
import { RightDrawer } from "./RightDrawer";
import { AgentLogDialog } from "./AgentLogDialog";
import { InlineConfirmBox } from "./InlineConfirmBox";
export function TicketChannel({
  pid,
  wid,
  tid,
}: {
  pid: string;
  wid: string;
  tid: string;
}) {
  const router = useRouter();
  const ticket = useQuery({
    queryKey: ["ticket", tid],
    queryFn: () => apiFetch<Ticket>(`/tickets/${tid}`),
  });
  const project = useQuery({
    queryKey: ["projects", pid],
    queryFn: () => apiFetch<Project>(`/projects/${pid}`),
    enabled: ticket.data?.project_id === pid,
  });
  const workflow = useQuery({
    queryKey: ["workflows", wid],
    queryFn: () => apiFetch<Workflow>(`/workflows/${wid}`),
    enabled: ticket.data?.workflow_id === wid,
  });
  const agents = useQuery({
    queryKey: ["projects", pid, "effective"],
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
    enabled: ticket.data?.project_id === pid,
  });
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<User>("/auth/me"),
  });
  useEffect(() => {
    if (
      ticket.data &&
      (ticket.data.project_id !== pid || ticket.data.workflow_id !== wid)
    )
      router.replace(
        `/projects/${ticket.data.project_id}/workflows/${ticket.data.workflow_id}/tickets/${tid}`,
      );
  }, [ticket.data, pid, wid, tid, router]);
  if (
    ticket.error ||
    project.error ||
    workflow.error ||
    agents.error ||
    me.error
  )
    return (
      <ErrorState
        error={
          ticket.error ||
          project.error ||
          workflow.error ||
          agents.error ||
          me.error
        }
      />
    );
  if (
    !ticket.data ||
    !project.data ||
    !workflow.data ||
    !agents.data ||
    !me.data
  )
    return <Loading />;
  return (
    <Channel
      key={tid}
      ticket={ticket.data}
      project={project.data}
      workflow={workflow.data}
      agents={agents.data}
      user={me.data}
    />
  );
}
function Channel({
  ticket,
  project,
  workflow,
  agents,
  user,
}: {
  ticket: Ticket;
  project: Project;
  workflow: Workflow;
  agents: Agent[];
  user: User;
}) {
  const client = useQueryClient();
  const tid = ticket.id;
  const [store] = useState(() => createTicketStore(ticket.status));
  const state = useStore(store);
  const [drawer, setDrawer] = useState(false);
  const [log, setLog] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [historyPage, setHistoryPage] = useState<HistoryPage | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const historyRequest = useRef<AbortController | null>(null);
  const olderBusy = useRef(false);
  const [error, setError] = useState<Error | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const root = useRef<HTMLDivElement>(null);
  const version = useQuery({
    queryKey: ["workflows", workflow.id, "version", ticket.workflow_version],
    queryFn: () =>
      apiFetch<{ graph: WorkflowGraph }>(
        `/workflows/${workflow.id}/versions/${ticket.workflow_version}`,
      ),
  });
  const config = useQuery({
    queryKey: ["ticket", tid, "chat-config"],
    queryFn: () =>
      apiFetch<{
        can_report: boolean;
        can_confirm: boolean;
        max_files: number;
        max_mb: number;
      }>(`/tickets/${tid}/chat-config`),
  });
  const members = useQuery({
    queryKey: ["projects", project.id, "members"],
    queryFn: () => apiFetch<Members>(`/projects/${project.id}/members`),
  });
  useEffect(() => {
    void useChatPrefs
      .getState()
      .load()
      .catch((e) => toast.error(e.message));
  }, []);
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    let socket: TicketSocket | undefined;
    async function load() {
      try {
        setError(null);
        setLoaded(false);
        setHistoryPage(null);
        const [runtime, history] = await Promise.all([
          apiFetch<RuntimeState>(`/tickets/${tid}/state`, {
            signal: controller.signal,
          }),
          loadTicketHistory(tid, controller.signal),
        ]);
        if (cancelled) return;
        store.getState().snapshot(runtime);
        store.setState({ afterSeq: history.last_seq });
        store.getState().history(history.groups);
        setHistoryPage(history);
        setLoaded(true);
        socket = new TicketSocket(tid, () => store.getState().afterSeq, {
          snapshot: (value) => store.getState().snapshot(value),
          connection: (connection) => {
            if (store.getState().connection !== connection)
              store.setState({ connection });
          },
          events: (events) => {
            store.getState().ingest(events);
            if (
              events.some((event) =>
                ["ticket_status", "gate_resolved"].includes(event.event_type),
              )
            ) {
              void client.invalidateQueries({ queryKey: ["ticket", tid] });
              void client.invalidateQueries({ queryKey: ["notifications"] });
            }
          },
        });
        socket.connect();
      } catch (e) {
        if (!cancelled) setError(e as Error);
      }
    }
    void load();
    return () => {
      cancelled = true;
      controller.abort();
      historyRequest.current?.abort();
      socket?.close();
    };
  }, [tid, store, client, loadAttempt]);
  async function loadOlder() {
    if (
      olderBusy.current ||
      !historyPage?.has_more ||
      historyPage.before_seq == null
    )
      return;
    olderBusy.current = true;
    setLoadingOlder(true);
    setHistoryError(null);
    const controller = new AbortController();
    historyRequest.current = controller;
    try {
      const page = await loadTicketHistory(
        tid,
        controller.signal,
        historyPage.before_seq,
        historyPage.last_seq,
      );
      if (controller.signal.aborted) return;
      store.getState().history(page.groups);
      setHistoryPage(page);
    } catch (error) {
      if (!controller.signal.aborted) setHistoryError((error as Error).message);
    } finally {
      olderBusy.current = false;
      if (!controller.signal.aborted) setLoadingOlder(false);
    }
  }
  const focusWaiting = state.status.startsWith("WAITING")
    ? state.waiting
    : null;
  const waitingKind = focusWaiting?.kind;
  const waitingNode = focusWaiting?.node_id;
  const waitingKey = focusWaiting?.payload.gate_key;
  useEffect(() => {
    if (!loaded || !waitingKind || !root.current) return;
    const timer = setTimeout(() => {
      const element = root.current?.querySelector(
        waitingKind === "human_confirm" ? "#confirm-box" : "#clarify-prompt",
      );
      element?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }, 50);
    return () => clearTimeout(timer);
  }, [loaded, waitingKind, waitingNode, waitingKey]);
  async function refresh() {
    const value = await apiFetch<RuntimeState>(`/tickets/${tid}/state`);
    store.getState().snapshot(value);
    await client.invalidateQueries({ queryKey: ["ticket", tid] });
  }
  async function confirm(approved: boolean, feedback?: string) {
    if (confirming) return;
    setConfirming(true);
    try {
      await send(`/tickets/${tid}/confirm`, { approved, feedback });
      await refresh();
    } catch (e) {
      await refresh();
      throw e;
    } finally {
      setConfirming(false);
    }
  }
  async function message(text: string, files: Attachment[], retryId?: string) {
    const id = retryId || clientId();
    store.getState().addPending({ id, text, attachments: files });
    try {
      const reply = store.getState().status === "WAITING_USER_INPUT";
      const result = await send<ChatEvent | { message: ChatEvent }>(
        `/tickets/${tid}/${reply ? "reply" : "messages"}`,
        {
          text: text || (reply ? "Xem tệp đính kèm." : ""),
          attachment_ids: files.map((f) => f.id),
          client_msg_id: id,
        },
      );
      store.getState().ingest(["message" in result ? result.message : result]);
    } catch (e) {
      store.getState().failPending(id);
      throw e;
    }
  }
  const latestTurn = state.groups.filter((g) => g.type === "turn").at(-1);
  const currentAgent = latestTurn?.agent || "Agent";
  const waiting = state.status.startsWith("WAITING") ? state.waiting : null;
  const release = (state.result || ticket.result || {}) as {
    commit_hash?: string;
    commit_url?: string;
    branch?: string;
    files?: string[];
    insertions?: number;
    deletions?: number;
  };
  const gateAttached = state.groups.some(
    (g) => g.type === "turn" && g.gate?.key === waiting?.payload.gate_key,
  );
  return (
    <div
      ref={root}
      data-testid="ticket-channel"
      className="-mx-3 -my-2 flex h-[calc(100dvh-80px)] min-h-[600px] flex-col overflow-hidden rounded-xl border border-stone-200 bg-white"
    >
      <ChannelHeader
        ticket={ticket}
        project={project}
        workflow={workflow}
        status={state.status}
        memberCount={agents.length + (members.data?.users.length || 1)}
        canReport={!!config.data?.can_report}
        canRelease={!!config.data?.can_confirm}
        onDrawer={() => setDrawer(true)}
        onAction={async (action) => {
          await send(`/tickets/${tid}/${action}`);
          await refresh();
        }}
      />
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {state.connection !== "connected" && loaded && (
            <div
              role="status"
              className="bg-amber-50 px-5 py-1 text-xs text-amber-800"
            >
              {state.connection === "reconnecting"
                ? "Đang kết nối lại…"
                : "Đang kết nối…"}
            </div>
          )}
          {error ? (
            <div className="p-5">
              <ErrorState error={error} />
              <button
                className="btn btn-light"
                onClick={() => setLoadAttempt((n) => n + 1)}
              >
                Tải lại tin nhắn
              </button>
            </div>
          ) : !loaded ? (
            <div
              role="status"
              className="min-h-0 flex-1 p-5 text-sm text-stone-500"
            >
              Đang tải tin nhắn mới nhất…
            </div>
          ) : (
            <MessageStream
              ticketId={tid}
              hasOlder={!!historyPage?.has_more}
              loadingOlder={loadingOlder}
              historyError={historyError}
              onLoadOlder={loadOlder}
              liveSeq={state.afterSeq}
              groups={state.groups}
              pending={state.pending}
              agents={agents}
              status={state.status}
              waiting={waiting}
              canConfirm={!!config.data?.can_confirm && !confirming}
              onConfirm={confirm}
              onLog={() => setLog(true)}
              onStop={
                config.data?.can_report
                  ? async () => {
                      try {
                        await send(`/tickets/${tid}/stop-agent`);
                        await refresh();
                      } catch (e) {
                        toast.error((e as Error).message);
                      }
                    }
                  : undefined
              }
              onRetry={(m: PendingMessage) =>
                void message(m.text, m.attachments, m.id).catch((e) =>
                  toast.error(e.message),
                )
              }
            />
          )}
          <div className="shrink-0 px-5 pt-2">
            {state.status === "CANCELLED" && config.data?.can_confirm && (
              <button
                className="btn btn-light mb-2"
                onClick={async () => {
                  if (
                    !window.confirm(
                      "Cất tất cả thay đổi chưa commit (kể cả file mới) trong workspace vào Git stash?",
                    )
                  )
                    return;
                  try {
                    await send(`/tickets/${tid}/stash`);
                    toast.success("Đã cất thay đổi vào Git stash");
                  } catch (e) {
                    toast.error((e as Error).message);
                  }
                }}
              >
                Hoàn tác thay đổi chưa commit (Git stash)
              </button>
            )}
            {waiting?.kind === "human_confirm" && !gateAttached && (
              <InlineConfirmBox
                gate={{
                  key: String(waiting.payload.gate_key),
                  kind: waiting.kind,
                  payload: waiting.payload,
                }}
                active
                canConfirm={!!config.data?.can_confirm && !confirming}
                onConfirm={confirm}
              />
            )}
            {waiting?.kind === "human_input" && (
              <div
                id="clarify-prompt"
                className="mb-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-xs text-sky-800"
              >
                <b>🐝 {currentAgent} đang chờ bạn cung cấp thêm chi tiết</b>
                <p className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap">
                  {String(
                    waiting.payload.question ||
                      "Hoàn tất kịch bản tái tạo lỗi bằng câu trả lời bên dưới.",
                  )}
                </p>
              </div>
            )}
            {state.status === "COMPLETED" && release.commit_hash && (
              <div className="mb-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                <b>Hoàn tất · </b>
                {release.commit_url ? (
                  <a
                    href={release.commit_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    {release.commit_hash}
                  </a>
                ) : (
                  <code>{release.commit_hash}</code>
                )}
                <button
                  className="ml-2 underline"
                  onClick={() =>
                    navigator.clipboard
                      .writeText(release.commit_hash!)
                      .catch(() => toast.error("Không thể sao chép commit"))
                  }
                >
                  Copy commit
                </button>{" "}
                · {release.branch} · +{release.insertions || 0} −
                {release.deletions || 0}
                <details className="mt-1">
                  <summary className="cursor-pointer">
                    File đã phát hành
                  </summary>
                  {release.files?.map((f) => (
                    <p key={f} className="font-mono">
                      {f}
                    </p>
                  ))}
                </details>
              </div>
            )}
            {state.status === "OPEN" ? (
              <button
                className="btn btn-dark mb-3"
                disabled={!loaded || !config.data?.can_report}
                onClick={async () => {
                  try {
                    await send(`/tickets/${tid}/start`);
                    await refresh();
                  } catch (e) {
                    toast.error((e as Error).message);
                  }
                }}
              >
                ▶ Bắt đầu xử lý
              </button>
            ) : null}
            <>
              {["COMPLETED", "CANCELLED"].includes(state.status) && (
                <p className="mb-2 text-xs text-stone-500">
                  Ticket đã kết thúc; không thể gửi thêm tin nhắn hoặc tệp.
                </p>
              )}
              <Composer
                tid={tid}
                userId={user.id}
                slug={ticket.channel_slug}
                agents={agents.filter((a) => a.is_active)}
                waiting={waiting}
                disabled={
                  config.data?.can_report === false ||
                  ["COMPLETED", "CANCELLED"].includes(state.status)
                }
                sendDisabled={!loaded || !config.data?.can_report || !!error}
                maxFiles={config.data?.max_files || 5}
                maxMb={config.data?.max_mb || 10}
                onSend={message}
              />
            </>
            <footer className="flex h-8 items-center justify-between gap-2 text-[11px] text-stone-500">
              <span className="truncate">
                {state.status === "COMPLETED"
                  ? release.commit_hash
                    ? `Hoàn tất: Commit ${release.commit_hash} đã được đẩy lên Git.`
                    : "Workflow đã hoàn tất"
                  : waiting
                    ? `${currentAgent}: Đang chờ người dùng ${waiting.kind === "human_confirm" ? "xác nhận để commit & push Git" : "trả lời"}…`
                    : `${currentAgent}: ${state.status === "RUNNING" ? latestTurn?.logLines.at(-1)?.text || "Đang làm việc…" : state.status}`}
              </span>
              <span className="shrink-0 font-mono text-[10px]">
                claude-agent-acp • codex-acp{" "}
                <span
                  className={
                    state.connection === "connected"
                      ? "text-emerald-500"
                      : "text-amber-500"
                  }
                >
                  ●
                </span>
              </span>
            </footer>
          </div>
        </div>
      </div>
      {drawer &&
        (version.data ? (
          <RightDrawer
            projectId={project.id}
            graph={version.data.graph}
            version={ticket.workflow_version}
            agents={agents}
            groups={state.groups}
            statuses={state.node_statuses}
            onClose={() => setDrawer(false)}
          />
        ) : (
          <div className="absolute right-5 top-20 rounded bg-white p-4 shadow">
            <ErrorState error={version.error} />
            <button onClick={() => setDrawer(false)}>Đóng</button>
          </div>
        ))}
      {log && (
        <AgentLogDialog
          tid={tid}
          lines={state.groups.flatMap((g) =>
            g.type === "turn" ? g.logLines : [],
          )}
          onClose={() => setLog(false)}
        />
      )}
    </div>
  );
}
