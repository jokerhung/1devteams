"use client";
import { useEffect, useState } from "react";
import {
  Check,
  CircleAlert,
  FileCode2,
  LoaderCircle,
} from "lucide-react";

export type TimelineAction = {
  id: string;
  title: string;
  status: string;
  kind?: "file" | "command";
  added?: number;
  removed?: number;
};

function ActionIcon({ action }: { action: TimelineAction }) {
  if (["failed", "error", "cancelled"].includes(action.status))
    return (
      <CircleAlert
        size={13}
        className="mt-0.5 shrink-0 text-red-600"
        aria-label="Lỗi"
      />
    );
  if (!["completed", "success", "done"].includes(action.status))
    return (
      <LoaderCircle
        size={13}
        className="mt-0.5 shrink-0 animate-spin"
        aria-label="Đang chạy"
      />
    );
  const Icon = action.kind === "file" ? FileCode2 : Check;
  return (
    <Icon
      size={13}
      className="mt-0.5 shrink-0 text-emerald-600"
      aria-label="Hoàn tất"
    />
  );
}

export function ActionTimeline({
  actions,
  startedAt,
  label,
}: {
  actions: TimelineAction[];
  startedAt: number;
  label: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const active = actions.findLast(
    (action) =>
      ![
        "completed",
        "success",
        "done",
        "failed",
        "error",
        "cancelled",
      ].includes(action.status),
  );
  function row(action: TimelineAction) {
    return (
      <li key={action.id} className="flex min-w-0 items-start gap-2 py-1">
        <ActionIcon action={action} />
        <span className="min-w-0 break-words font-mono text-[11px]">
          {action.title.slice(0, 1000)}
        </span>
        {action.added != null && (
          <span className="shrink-0 text-emerald-600">+{action.added}</span>
        )}
        {action.removed != null && (
          <span className="shrink-0 text-red-600">−{action.removed}</span>
        )}
      </li>
    );
  }
  return (
    <div className="my-3 space-y-2 text-xs text-stone-500">
      {!!actions.length && (
        <div className="border-l border-stone-200 pl-3">
          {actions.length > 5 && (
            <details className="mb-1">
              <summary className="cursor-pointer py-1 text-[11px]">
                {actions.length - 5} thao tác trước
              </summary>
              <ol aria-label="Thao tác trước đó">
                {actions.slice(0, -5).map(row)}
              </ol>
            </details>
          )}
          <ol aria-label="5 hành động gần nhất">
            {actions.slice(-5).map(row)}
          </ol>
        </div>
      )}
      <div
        role="status"
        className="flex min-w-0 items-center gap-2 border-t border-stone-100 pt-2"
      >
        <LoaderCircle
          size={14}
          className="shrink-0 animate-spin"
          aria-label="Đang xử lý"
        />
        <span className="shrink-0">Đang chạy…</span>
        <span
          className="min-w-0 truncate font-mono text-[11px]"
          title={active?.title || label}
        >
          {active?.title || label}
        </span>
        <span
          className="ml-auto shrink-0 tabular-nums"
          aria-label="Thời gian chạy"
        >
          {Math.max(0, Math.floor((now - startedAt) / 1000))}s
        </span>
      </div>
    </div>
  );
}
