"use client";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import { Modal } from "@/components/ui-app/primitives";
import { logColors, logTime } from "./AgentLog";
import { toLogLine } from "./groupEvents";
import type { ChatEvent, LogLine } from "./types";
export function AgentLogDialog({
  tid,
  lines,
  onClose,
}: {
  tid: string;
  lines: LogLine[];
  onClose: () => void;
}) {
  const [agent, setAgent] = useState("");
  const [history, setHistory] = useState<LogLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState(0);
  const [more, setMore] = useState(true);
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const all = [
    ...new Map([...history, ...lines].map((line) => [line.seq, line])).values(),
  ].sort((a, b) => a.seq - b.seq);
  const filtered = all.filter((l) => !agent || l.agent === agent);
  useEffect(() => {
    if (bottom.current && scroll.current)
      scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [filtered.length]);
  async function load() {
    setBusy(true);
    try {
      const rows = await apiFetch<
        {
          seq: number;
          run_id: string | null;
          agent: string;
          kind: string;
          text: string;
          at: string;
          metadata: Record<string, unknown>;
        }[]
      >(`/tickets/${tid}/logs?after_seq=${cursor}&limit=500`);
      setHistory((prev) => [
        ...prev,
        ...rows
          .map((r) =>
            toLogLine({
              seq: r.seq,
              content: r.text,
              event_type: r.kind,
              sender_name: r.agent,
              created_at: r.at,
              metadata: r.metadata || {},
            } as ChatEvent),
          )
          .filter((r): r is LogLine => !!r),
      ]);
      setCursor(rows.at(-1)?.seq || cursor);
      setMore(rows.length === 500);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Toàn bộ log của ticket" wide onClose={onClose}>
      <div className="mb-3 flex items-center gap-3 text-xs">
        <select
          aria-label="Lọc log theo agent"
          className="inp !w-auto"
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
        >
          <option value="">Tất cả agent</option>
          {[...new Set(all.map((l) => l.agent))].map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <span>{filtered.length} dòng</span>
        <button
          className="btn btn-light"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(
                filtered
                  .map((l) => `${logTime(l.at)} ${l.agent} ${l.text}`)
                  .join("\n"),
              );
              toast.success("Đã sao chép log");
            } catch {
              toast.error("Không thể sao chép log");
            }
          }}
        >
          Copy
        </button>
        {more && (
          <button
            disabled={busy}
            className="btn btn-light"
            onClick={() => void load()}
          >
            Tải lịch sử log
          </button>
        )}
      </div>
      <div
        ref={scroll}
        onScroll={(e) => {
          const el = e.currentTarget;
          bottom.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
        className="h-[60vh] overflow-auto rounded-xl bg-stone-950 p-4 font-mono text-[11px]"
      >
        {filtered.map((l) => (
          <div
            key={l.seq}
            className={`whitespace-pre-wrap break-all py-0.5 ${logColors[l.kind]}`}
          >
            {logTime(l.at)} {l.agent} {l.text}
          </div>
        ))}
      </div>
    </Modal>
  );
}
