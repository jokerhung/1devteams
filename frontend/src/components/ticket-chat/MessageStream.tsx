"use client";
import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Agent } from "@/lib/types";
import type { MessageGroup, PendingMessage, Waiting } from "./types";
import { AgentTurn } from "./AgentTurn";
import { UserMessage } from "./UserMessage";
import { MessageAttachments } from "./MessageAttachments";
export function MessageStream({
  groups,
  pending,
  agents,
  status,
  waiting,
  canConfirm,
  onConfirm,
  onLog,
  onRetry,
}: {
  groups: MessageGroup[];
  pending: PendingMessage[];
  agents: Agent[];
  status: string;
  waiting: Waiting | null;
  canConfirm: boolean;
  onConfirm: (approved: boolean, feedback?: string) => Promise<void>;
  onLog: () => void;
  onRetry: (message: PendingMessage) => void;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const [newMessages, setNew] = useState(false);
  const virtual = useVirtualizer({
    count: groups.length > 300 ? groups.length : 0,
    getScrollElement: () => scroll.current,
    estimateSize: () => 160,
    overscan: 8,
    getItemKey: (i) => groups[i].id,
  });
  useEffect(() => {
    if (bottom.current && scroll.current) {
      scroll.current.scrollTop = scroll.current.scrollHeight;
      setNew(false);
    } else setNew(true);
  }, [groups, pending]);
  useEffect(() => {
    const observer = new ResizeObserver(() => {
      if (bottom.current && scroll.current)
        scroll.current.scrollTop = scroll.current.scrollHeight;
    });
    if (scroll.current?.firstElementChild)
      observer.observe(scroll.current.firstElementChild);
    return () => observer.disconnect();
  }, []);
  const render = (group: MessageGroup) =>
    group.type === "user" ? (
      <>
        <UserMessage event={group.event} agents={agents} />
        {group.event.metadata.initial === true && (
          <div className="my-4 flex items-center gap-3 text-[11px] text-stone-400">
            <span className="h-px flex-1 bg-stone-200" />
            Tiến trình Đội ngũ Agent
            <span className="h-px flex-1 bg-stone-200" />
          </div>
        )}
      </>
    ) : group.type === "system" ? (
      <div className="my-4 text-center text-xs text-stone-500">
        {group.text}
      </div>
    ) : (
      <AgentTurn
        turn={group}
        agents={agents}
        running={!group.endedAt && status === "RUNNING" && !group.failed}
        activeGate={
          !!waiting &&
          group.gate?.key === waiting.payload.gate_key &&
          status === "WAITING_USER_CONFIRM"
        }
        canConfirm={canConfirm}
        onConfirm={onConfirm}
        onLog={onLog}
      />
    );
  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scroll}
        data-testid="message-stream"
        role="log"
        aria-label="Tin nhắn ticket"
        className="h-full overflow-y-auto px-5 py-4"
        onScroll={(e) => {
          const el = e.currentTarget;
          bottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          if (bottom.current) setNew(false);
        }}
      >
        <div className="mx-auto max-w-5xl">
          {groups.length > 300 ? (
            <div
              className="relative w-full"
              style={{ height: virtual.getTotalSize() }}
            >
              {virtual.getVirtualItems().map((item) => (
                <div
                  key={item.key}
                  ref={virtual.measureElement}
                  data-index={item.index}
                  className="absolute left-0 top-0 w-full pb-3"
                  style={{ transform: `translateY(${item.start}px)` }}
                >
                  {render(groups[item.index])}
                </div>
              ))}
            </div>
          ) : (
            groups.map((group) => (
              <div key={group.id} className="mb-3">
                {render(group)}
              </div>
            ))
          )}
          {pending.map((m) => (
            <div
              key={m.id}
              className="my-3 rounded-lg border border-stone-100 p-3 text-xs text-stone-500"
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              <MessageAttachments files={m.attachments} />
              {m.failed ? (
                <button
                  className="mt-2 text-red-700 underline"
                  onClick={() => onRetry(m)}
                >
                  Gửi thất bại — Thử lại
                </button>
              ) : (
                <span>Đang gửi…</span>
              )}
            </div>
          ))}
        </div>
      </div>
      {newMessages && (
        <button
          className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs shadow-md"
          onClick={() => {
            bottom.current = true;
            scroll.current?.scrollTo({
              top: scroll.current.scrollHeight,
              behavior: "smooth",
            });
            setNew(false);
          }}
        >
          Tin mới ↓
        </button>
      )}
    </div>
  );
}
