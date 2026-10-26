"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  MessageSquare,
  Send,
  PanelRightClose,
  PanelRightOpen,
  Trash2,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { graphKey, serialize, type WorkflowGraph } from "./serialize";
import type { WorkflowStore } from "./store";

type Message = {
  role: "user" | "assistant";
  content: string;
  graph?: WorkflowGraph;
  applied?: boolean;
};
type Reply = { message: string; graph: WorkflowGraph | null; errors: string[] };

export function WorkflowAssistantPanel({
  endpoint,
  store,
  disabled,
  onApplied,
  children,
}: {
  endpoint: string;
  store: WorkflowStore;
  disabled: boolean;
  onApplied: () => void;
  children: ReactNode;
}) {
  const [tab, setTab] = useState<"chat" | "node">("chat");
  const [collapsed, setCollapsed] = useState(false);
  const [width, setWidth] = useState(280);
  const [maxWidth, setMaxWidth] = useState(720);
  const [resizing, setResizing] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const readOnly = useRef(disabled);
  readOnly.current = disabled;
  useEffect(() => {
    const container = panel.current?.parentElement;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      setMaxWidth(Math.max(280, Math.min(720, container.clientWidth - 240)));
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [collapsed]);
  const resize = (value: number) => {
    const next = Math.round(Math.max(280, Math.min(maxWidth, value)));
    setWidth(next);
  };
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [messages, busy]);
  const apply = (graph: WorkflowGraph) => {
    if (readOnly.current) return;
    store.getState().replace(graph);
    onApplied();
  };
  const submit = async () => {
    if (busy || disabled || !text.trim()) return;
    const next: Message[] = [
      ...messages,
      { role: "user", content: text.trim() },
    ];
    const snapshot = store.getState(),
      key = graphKey(snapshot);
    setMessages(next);
    setText("");
    setError("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      const response = await apiFetch<Reply>(endpoint, {
        method: "POST",
        signal: abort.current.signal,
        body: JSON.stringify({
          graph: serialize(snapshot),
          messages: next.slice(-20).map(({ role, content }) => ({
            role,
            content: content.slice(0, 12000),
          })),
        }),
      });
      const canApply =
        !!response.graph &&
        graphKey(store.getState()) === key &&
        !readOnly.current;
      if (canApply) apply(response.graph!);
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          content:
            response.message +
            (response.errors.length
              ? "\n\nSơ đồ chưa được áp dụng:\n" + response.errors.join("\n")
              : ""),
          graph: response.graph || undefined,
          applied: canApply,
        },
      ]);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  if (collapsed)
    return (
      <aside className="shrink-0 border-l border-stone-200 p-2">
        <button
          type="button"
          className="btn btn-light !p-2"
          aria-label="Mở panel workflow"
          title="Mở chat @workflow"
          onClick={() => setCollapsed(false)}
        >
          <PanelRightOpen size={16} />
        </button>
      </aside>
    );
  return (
    <aside
      ref={panel}
      aria-label="Trợ lý workflow"
      style={{ width: Math.min(width, maxWidth) }}
      className={`relative flex shrink-0 flex-col border-l border-stone-200 bg-white ${resizing ? "select-none" : ""}`}
    >
      <div
        role="separator"
        aria-label="Đổi chiều rộng panel workflow"
        aria-orientation="vertical"
        aria-valuemin={280}
        aria-valuemax={maxWidth}
        aria-valuenow={Math.min(width, maxWidth)}
        tabIndex={0}
        title="Kéo để đổi chiều rộng panel"
        className="group absolute inset-y-0 -left-1.5 z-20 flex w-3 touch-none cursor-col-resize items-center justify-center outline-none hover:bg-sky-100/60 focus-visible:bg-sky-100"
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = { x: event.clientX, width: Math.min(width, maxWidth) };
          setResizing(true);
        }}
        onPointerMove={(event) => {
          if (drag.current)
            resize(drag.current.width + drag.current.x - event.clientX);
        }}
        onPointerUp={(event) => {
          drag.current = null;
          setResizing(false);
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={() => {
          drag.current = null;
          setResizing(false);
        }}
        onLostPointerCapture={() => {
          drag.current = null;
          setResizing(false);
        }}
        onKeyDown={(event) => {
          const current = Math.min(width, maxWidth);
          const next = {
            ArrowLeft: current + 20,
            ArrowRight: current - 20,
            Home: 280,
            End: maxWidth,
          }[event.key];
          if (next !== undefined) {
            event.preventDefault();
            resize(next);
          }
        }}
      >
        <span className="h-10 w-1 rounded-full bg-stone-300 group-hover:bg-sky-400 group-focus-visible:bg-sky-400" />
      </div>
      <header className="flex flex-wrap items-center gap-1 border-b border-stone-200 p-2">
        <button
          type="button"
          className={`btn gap-1 text-xs ${tab === "chat" ? "btn-dark" : "btn-light"}`}
          aria-pressed={tab === "chat"}
          onClick={() => setTab("chat")}
        >
          <MessageSquare size={14} />
          @workflow
        </button>
        <button
          type="button"
          className={`btn text-xs ${tab === "node" ? "btn-dark" : "btn-light"}`}
          aria-pressed={tab === "node"}
          onClick={() => setTab("node")}
        >
          Cấu hình node
        </button>
        <button
          type="button"
          className="ml-auto rounded p-1 text-stone-500 hover:bg-stone-100 disabled:opacity-30"
          aria-label="Xóa hội thoại workflow"
          title="Xóa hội thoại"
          disabled={busy || !messages.length}
          onClick={() => {
            setMessages([]);
            setError("");
            setText("");
          }}
        >
          <Trash2 size={14} />
        </button>
        <button
          type="button"
          className="rounded p-1 text-stone-500 hover:bg-stone-100"
          aria-label="Thu gọn panel workflow"
          onClick={() => setCollapsed(true)}
        >
          <PanelRightClose size={16} />
        </button>
      </header>
      <div
        hidden={tab !== "node"}
        className="min-h-0 flex-1 overflow-y-auto [&>aside]:w-full [&>aside]:border-l-0"
      >
        {children}
      </div>
      <div
        hidden={tab !== "chat"}
        className={tab === "chat" ? "flex min-h-0 flex-1 flex-col" : "hidden"}
      >
        <p className="border-b border-stone-100 px-3 py-2 text-xs leading-5 text-stone-500">
          Mô tả luồng cần tạo hoặc thay đổi. Đề xuất hợp lệ được áp dụng vào
          canvas; dùng Hoàn tác để quay lại, Lưu để giữ thay đổi.
        </p>
        <div
          className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3"
          aria-live="polite"
        >
          {!messages.length && (
            <p className="text-xs leading-6 text-stone-400">
              Ví dụ: “Tạo luồng fix bug gồm BA, Developer, Tester, chờ user xác
              nhận rồi DevOps commit.”
            </p>
          )}
          {messages.map((message, index) => (
            <div
              key={index}
              className={`rounded-xl p-3 text-xs leading-6 ${message.role === "user" ? "bg-sky-50" : "bg-stone-50"}`}
            >
              <b className="mb-1 block">
                {message.role === "user" ? "Bạn" : "@workflow"}
              </b>
              <p className="whitespace-pre-wrap break-words">
                {message.content}
              </p>
              {message.applied && (
                <p className="mt-2 text-emerald-700">
                  Đã cập nhật canvas · chưa lưu
                </p>
              )}
              {message.graph && !message.applied && (
                <div className="mt-2">
                  <p className="text-amber-700">
                    Canvas đã thay đổi trong lúc chờ phản hồi. Đề xuất chưa được
                    áp dụng.
                  </p>
                  <button
                    type="button"
                    className="btn btn-light mt-2"
                    disabled={disabled || busy}
                    onClick={() => {
                      apply(message.graph!);
                      setMessages((previous) =>
                        previous.map((item, i) =>
                          i === index ? { ...item, applied: true } : item,
                        ),
                      );
                    }}
                  >
                    Áp dụng đề xuất
                  </button>
                </div>
              )}
            </div>
          ))}
          {busy && (
            <p role="status" className="text-xs text-stone-500">
              @workflow đang xử lý…
            </p>
          )}
          <div ref={end} />
        </div>
        {error && (
          <div role="alert" className="px-3 pb-2 text-xs text-red-700">
            {error}
            <button
              type="button"
              className="ml-2 underline"
              disabled={disabled || busy}
              onClick={() =>
                setText(
                  messages.filter((m) => m.role === "user").at(-1)?.content ||
                    "",
                )
              }
            >
              Soạn lại
            </button>
          </div>
        )}
        <form
          className="space-y-2 border-t border-stone-200 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <textarea
            aria-label="Nhắn @workflow"
            placeholder="Nhắn @workflow để tạo hoặc sửa luồng…"
            className="inp min-h-24 resize-none text-xs"
            maxLength={12000}
            value={text}
            disabled={disabled || busy}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault();
                void submit();
              }
            }}
          />
          <div className="flex items-center justify-between text-xs text-stone-400">
            <span>{disabled ? "Chỉ xem" : "Ctrl/⌘ + Enter để gửi"}</span>
            <button
              type="submit"
              className="btn btn-dark gap-1"
              disabled={disabled || busy || !text.trim()}
            >
              <Send size={13} />
              Gửi
            </button>
          </div>
        </form>
      </div>
    </aside>
  );
}
