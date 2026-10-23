"use client";
import { eventDate } from "./time";
import { useEffect, useRef, useState } from "react";
import type { LogLine } from "./types";
export const logColors = {
  info: "text-stone-400",
  tool: "text-stone-600",
  perm: "text-amber-700",
  deny: "text-red-600",
  think: "text-purple-600",
  ok: "text-emerald-600",
  error: "text-red-600",
};
export const logTime = (at: string) =>
  eventDate(at).toLocaleTimeString("vi-VN", { hour12: false });
export function AgentLog({
  lines,
  running,
  onFull,
}: {
  lines: LogLine[];
  running: boolean;
  onFull: () => void;
}) {
  const [open, setOpen] = useState(false);
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  useEffect(() => {
    if (open && bottom.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [lines.length, open]);
  if (!lines.length) return null;
  const last = lines[lines.length - 1];
  return (
    <div data-testid="agent-log" className="my-1 min-w-0 font-mono text-[11px]">
      <button
        aria-label="Mở log lượt agent"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 text-left"
      >
        {running && (
          <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-emerald-500" />
        )}
        <span className={`min-w-0 flex-1 truncate ${logColors[last.kind]}`}>
          {last.text}
        </span>
        <span>{open ? "⌃" : "⌄"}</span>
      </button>
      {open && (
        <div
          ref={scroll}
          onScroll={(e) => {
            const el = e.currentTarget;
            bottom.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          }}
          className="my-2 max-h-64 overflow-y-auto rounded-lg border border-stone-200 bg-white p-2"
        >
          {lines.map((line) => (
            <div
              key={line.seq}
              className={`flex gap-3 py-0.5 ${logColors[line.kind]}`}
            >
              <span className="flex-1 whitespace-pre-wrap break-all">
                {line.text}
              </span>
              <time className="shrink-0 text-stone-400">
                {logTime(line.at)}
              </time>
            </div>
          ))}
          <button className="mt-2 text-sky-700 underline" onClick={onFull}>
            Xem toàn bộ log của ticket →
          </button>
        </div>
      )}
    </div>
  );
}
