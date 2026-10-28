"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  ChevronDown,
  Folder,
  MessageSquare,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { apiFetch, apiStream } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import type { Agent } from "@/lib/types";
import { allProjects } from "@/lib/projects";
import { MarkdownContent } from "@/components/ticket-chat/blocks/MarkdownContent";
import { ChatImage } from "./chat-image";
import { ActionTimeline } from "./action-timeline";

type BrowserReport = {
  test_case: string;
  status: string;
  summary: string;
  url: string;
  checks: unknown[];
  screenshot?: string;
};
type Message = {
  role: "user" | "assistant";
  content: string;
  reports?: BrowserReport[];
};
type Conversation = { messages: Message[]; draft: string };
type Action = { id: string; title: string; status: string };
type ChatEvent =
  | ({ type: "action" } & Action)
  | { type: "reply"; message: string; reports?: BrowserReport[] }
  | { type: "error"; message: string };

export function AgentChat({
  open,
  onClose,
  contextProjectId,
}: {
  open: boolean;
  onClose: () => void;
  contextProjectId?: string;
}) {
  const agents = useQuery({
    queryKey: keys.agents,
    queryFn: () => apiFetch<Agent[]>("/agents"),
    enabled: open,
  });
  const available = (agents.data || []).filter((agent) => agent.is_active);
  const projects = useQuery({
    queryKey: [...keys.projects, "list"],
    queryFn: allProjects,
    enabled: open,
  });
  const [projectId, setProjectId] = useState("");
  const [selected, setSelected] = useState("");
  const agentId = selected || available[0]?.id || "";
  const agent = available.find((item) => item.id === agentId);
  const [conversations, setConversations] = useState<
    Record<string, Conversation>
  >({});
  const conversationKey = `${agentId}:${projectId}`;
  const conversation = conversations[conversationKey] || {
    messages: [],
    draft: "",
  };
  const [startedAt, setStartedAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState("");
  const [actions, setActions] = useState<Action[]>([]);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  useEffect(() => {
    const opening = open && !wasOpen.current;
    wasOpen.current = open;
    if (opening && !busy) {
      setProjectId(contextProjectId || "");
      setError("");
    }
  }, [open, contextProjectId, busy]);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    if (open) end.current?.scrollIntoView({ block: "nearest" });
  }, [open, conversation.messages, busy, actions]);

  function update(value: Partial<Conversation>) {
    setConversations((previous) => ({
      ...previous,
      [conversationKey]: {
        ...(previous[conversationKey] || { messages: [], draft: "" }),
        ...value,
      },
    }));
  }

  async function submit() {
    if (busy || !agent || !conversation.draft.trim()) return;
    const messages: Message[] = [
      ...conversation.messages,
      { role: "user", content: conversation.draft.trim() },
    ];
    const draft = conversation.draft;
    update({ draft: "" });
    setError("");
    setStartedAt(Date.now());
    setBusy(true);
    setActions([]);
    setPending(draft.trim());
    const controller = new AbortController();
    abort.current = controller;
    try {
      let received = false;
      await apiStream<ChatEvent>(
        "/agent-chat",
        {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify({
            agent_id: agentId,
            project_id: projectId || null,
            messages: messages
              .slice(-39)
              .map(({ role, content }) => ({ role, content })),
          }),
        },
        (event) => {
          if (event.type === "action") {
            setActions((previous) =>
              [
                ...previous.filter((action) => action.id !== event.id),
                event,
              ].slice(-200),
            );
          } else if (event.type === "error") {
            throw new Error(event.message);
          } else {
            received = true;
            update({
              messages: [
                ...messages,
                {
                  role: "assistant",
                  content: event.message,
                  reports: event.reports,
                },
              ],
            });
          }
        },
      );
      if (!received)
        throw new Error(
          "Kết nối bị ngắt trước khi agent trả lời. Hãy thử lại.",
        );
    } catch (e) {
      update({ draft });
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setBusy(false);
      setPending("");
    }
  }

  return (
    <aside
      id="agent-chat-panel"
      aria-label="Chat với AI Agent"
      hidden={!open}
      className={
        open
          ? "fixed inset-3 z-40 flex min-h-0 flex-col rounded-xl border border-stone-200 bg-white shadow-lg lg:static lg:z-auto lg:w-[400px] lg:shrink-0 lg:rounded-none lg:border-0 lg:border-l lg:shadow-none"
          : "hidden"
      }
    >
      <header className="flex items-center gap-2 border-b border-stone-200 p-3">
        <MessageSquare size={16} />
        <h2 className="flex-1 text-sm font-semibold">Chat với AI Agent</h2>
        <button
          type="button"
          aria-label="Cuộc trò chuyện mới"
          title="Cuộc trò chuyện mới"
          className="btn btn-light !p-2"
          disabled={busy || !conversation.messages.length}
          onClick={() => {
            update({ messages: [], draft: "" });
            setError("");
          }}
        >
          <Trash2 size={15} />
        </button>
        <button
          type="button"
          aria-label="Đóng chat với AI Agent"
          className="btn btn-light !p-2"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </header>
      <div className="border-b border-stone-100 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Folder
              size={14}
              className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-stone-500"
              aria-hidden
            />
            <label htmlFor="chat-project" className="sr-only">
              Project
            </label>
            <select
              id="chat-project"
              className="h-8 w-full min-w-0 appearance-none truncate rounded-md border border-stone-200 bg-transparent pl-7 pr-6 text-xs outline-none focus:ring-2 focus:ring-sky-200 disabled:opacity-50"
              title={
                projects.data?.items.find((project) => project.id === projectId)
                  ?.name || "Không chọn project"
              }
              value={projectId}
              disabled={busy || projects.isPending}
              onChange={(event) => {
                setProjectId(event.target.value);
                setError("");
              }}
            >
              <option value="">Không chọn project</option>
              {(projects.data?.items || []).map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
            <ChevronDown
              size={13}
              className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-stone-500"
              aria-hidden
            />
          </div>
          <div className="relative min-w-0 flex-1">
            <Bot
              size={14}
              className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-stone-500"
              aria-hidden
            />
            <label htmlFor="chat-agent" className="sr-only">
              AI Agent
            </label>
            <select
              id="chat-agent"
              className="h-8 w-full min-w-0 appearance-none truncate rounded-md border border-stone-200 bg-transparent pl-7 pr-6 text-xs outline-none focus:ring-2 focus:ring-sky-200 disabled:opacity-50"
              title={
                agent
                  ? `${agent.display_name} (${agent.handle})${agent.description ? ` — ${agent.description}` : ""}`
                  : "AI Agent"
              }
              value={agentId}
              disabled={busy || !available.length}
              onChange={(event) => {
                setSelected(event.target.value);
                setError("");
              }}
            >
              {!available.length && (
                <option value="">Chưa có agent hoạt động</option>
              )}
              {available.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name} ({item.handle})
                </option>
              ))}
            </select>
            <ChevronDown
              size={13}
              className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-stone-500"
              aria-hidden
            />
          </div>
        </div>
        {projects.error && (
          <p role="alert" className="mt-2 text-xs text-red-700">
            Không tải được danh sách project: {projects.error.message}
          </p>
        )}
      </div>
      <div
        className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3"
        role="log"
        aria-label="Hội thoại với AI Agent"
        aria-busy={busy}
      >
        {!conversation.messages.length && (
          <p className="py-6 text-center text-sm text-stone-400">
            Chọn AI Agent và nhập tin nhắn để bắt đầu.
          </p>
        )}
        {conversation.messages.map((message, index) => (
          <div
            key={index}
            className={`min-w-0 rounded-xl p-3 text-sm ${message.role === "user" ? "bg-sky-50" : "bg-stone-50"}`}
          >
            <b className="mb-2 block text-xs text-stone-500">
              {message.role === "user"
                ? "Bạn"
                : `${agent?.display_name || "Agent"} ${agent?.handle || ""}`}
            </b>
            {message.role === "assistant" ? (
              <MarkdownContent text={message.content} />
            ) : (
              <p className="whitespace-pre-wrap break-words">
                {message.content}
              </p>
            )}
            {message.reports?.map((report, reportIndex) => (
              <section
                key={reportIndex}
                aria-label={`Kết quả test ${report.test_case}`}
                className="mt-3 space-y-2 rounded-lg border border-stone-200 bg-white p-2 text-xs"
              >
                <p className="font-semibold">
                  {report.status} · {report.test_case}
                </p>
                <p>{report.summary}</p>
                <p className="break-all text-stone-500">{report.url}</p>
                <p>{report.checks.length} kiểm tra thực tế</p>
                {report.screenshot && (
                  <ChatImage
                    src={report.screenshot}
                    alt={`Screenshot ${report.test_case}`}
                  />
                )}
              </section>
            ))}
          </div>
        ))}
        {busy && (
          <div role="status" className="space-y-2 text-xs text-stone-500">
            <p className="whitespace-pre-wrap rounded-xl bg-sky-50 p-3">
              {pending}
            </p>
            <ActionTimeline
              actions={actions}
              startedAt={startedAt}
              label={`${agent?.display_name || "Agent"} đang trả lời…`}
            />
          </div>
        )}
        <div ref={end} />
      </div>
      {(error || agents.error) && (
        <p role="alert" className="px-3 py-2 text-xs text-red-700">
          {error || agents.error?.message}
        </p>
      )}
      <form
        className="space-y-2 border-t border-stone-200 p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <textarea
          aria-label="Tin nhắn cho AI Agent"
          placeholder="Nhập tin nhắn…"
          className="inp min-h-24 resize-none text-sm"
          maxLength={12000}
          disabled={busy || !agent}
          value={conversation.draft}
          onChange={(event) => update({ draft: event.target.value })}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              (event.ctrlKey || event.metaKey) &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void submit();
            }
          }}
        />
        <div className="flex items-center justify-between text-xs text-stone-400">
          <span>Ctrl/⌘ + Enter để gửi</span>
          <button
            type="submit"
            className="btn btn-dark gap-1"
            disabled={busy || !agent || !conversation.draft.trim()}
          >
            <Send size={14} />
            Gửi
          </button>
        </div>
      </form>
    </aside>
  );
}
