"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { Agent } from "@/lib/types";
import type { MessageGroup, PendingMessage, Waiting } from "./types";
import { AgentTurn } from "./AgentTurn";
import { UserMessage } from "./UserMessage";
import { MessageAttachments } from "./MessageAttachments";
export function MessageStream({
  ticketId,
  groups,
  pending,
  agents,
  status,
  waiting,
  canConfirm,
  onConfirm,
  onLog,
  onRetry,
  onStop,
  hasOlder,
  loadingOlder,
  historyError,
  onLoadOlder,
  liveSeq,
}: {
  ticketId: string;
  groups: MessageGroup[];
  pending: PendingMessage[];
  agents: Agent[];
  status: string;
  waiting: Waiting | null;
  canConfirm: boolean;
  onConfirm: (approved: boolean, feedback?: string) => Promise<void>;
  onLog: () => void;
  onRetry: (message: PendingMessage) => void;
  onStop?: () => void;
  hasOlder: boolean;
  loadingOlder: boolean;
  historyError: string | null;
  onLoadOlder: () => Promise<void>;
  liveSeq: number;
}) {
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const previousTop = useRef(0);
  const latestId = useRef(groups.at(-1)?.id);
  const latestSeq = useRef(liveSeq);
  const [newMessages, setNew] = useState(false);
  const virtual = useVirtualizer({
    count: groups.length,
    getScrollElement: () => scroll.current,
    estimateSize: () => 160,
    overscan: 2,
    getItemKey: (i) => groups[i].id,
    anchorTo: "end",
    followOnAppend: true,
    scrollEndThreshold: 80,
  });
  function loadOlder() {
    if (!hasOlder || loadingOlder || !scroll.current) return;
    bottom.current = false;
    void onLoadOlder();
  }
  useLayoutEffect(() => {
    if (bottom.current && scroll.current) {
      virtual.scrollToIndex(groups.length - 1, { align: "end" });
      scroll.current.scrollTop = scroll.current.scrollHeight;
      setNew(false);
    } else if (
      groups.at(-1)?.id !== latestId.current ||
      liveSeq > latestSeq.current
    )
      setNew(true);
    latestId.current = groups.at(-1)?.id;
    latestSeq.current = liveSeq;
  }, [groups, pending, virtual, liveSeq]);
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
        ticketId={ticketId}
        turn={group}
        agents={agents}
        running={
          !group.endedAt &&
          (status === "RUNNING" || group.nodeId === "adhoc") &&
          !group.failed
        }
        activeGate={
          !!waiting &&
          group.gate?.key === waiting.payload.gate_key &&
          status === "WAITING_USER_CONFIRM"
        }
        canConfirm={canConfirm}
        onConfirm={onConfirm}
        onLog={onLog}
        onStop={onStop}
      />
    );
  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scroll}
        data-testid="message-stream"
        data-message-count={groups.length}
        role="log"
        aria-label="Tin nhắn ticket"
        className="h-full overflow-y-auto px-5 py-4"
        style={{ overflowAnchor: "none" }}
        onWheel={(event) => {
          if (
            event.deltaY < 0 &&
            event.currentTarget.scrollTop < 120 &&
            !historyError
          )
            loadOlder();
        }}
        onScroll={(e) => {
          const el = e.currentTarget;
          bottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          if (bottom.current) setNew(false);
          if (
            el.scrollTop < previousTop.current &&
            el.scrollTop < 120 &&
            !historyError
          )
            loadOlder();
          previousTop.current = el.scrollTop;
        }}
      >
        <div className="mx-auto max-w-5xl">
          {hasOlder && (
            <div className="absolute left-1/2 top-1 z-10 -translate-x-1/2">
              <button
                className="rounded border border-stone-200 bg-white px-2 py-1 text-xs shadow-sm"
                disabled={loadingOlder}
                onClick={loadOlder}
              >
                {loadingOlder
                  ? "Đang tải…"
                  : historyError
                    ? "Tải lại lịch sử cũ"
                    : "↑ Tải 10 tin nhắn trước"}
              </button>
              {historyError && (
                <p role="alert" className="bg-white text-xs text-red-700">
                  {historyError}
                </p>
              )}
            </div>
          )}
          <div
            className="relative w-full"
            style={{ height: virtual.getTotalSize() }}
          >
            {virtual.getVirtualItems().map((item) => (
              <div
                key={item.key}
                ref={virtual.measureElement}
                data-index={item.index}
                data-message-id={groups[item.index].id}
                className="absolute left-0 top-0 w-full pb-3"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                {render(groups[item.index])}
              </div>
            ))}
          </div>
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
