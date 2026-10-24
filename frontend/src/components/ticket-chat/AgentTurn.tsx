"use client";
import { eventDate } from "./time";
import type { Agent } from "@/lib/types";
import { Logo } from "@/components/ui-app/primitives";
import { TurnDetails } from "./TurnDetails";
import { MarkdownContent } from "./blocks/MarkdownContent";
import { InlineConfirmBox } from "./InlineConfirmBox";
import { cleanContent } from "./groupEvents";
import type { TurnGroup } from "./types";
export function AgentTurn({
  ticketId,
  turn,
  agents,
  running,
  activeGate,
  canConfirm,
  onConfirm,
  onLog,
  onStop,
}: {
  ticketId: string;
  turn: TurnGroup;
  agents: Agent[];
  running: boolean;
  activeGate: boolean;
  canConfirm: boolean;
  onConfirm: (approved: boolean, feedback?: string) => Promise<void>;
  onLog: () => void;
  onStop?: () => void;
}) {
  const agent = agents.find((a) => a.handle === turn.agent);
  const api = turn.runtime === "openai-api" || agent?.runtime === "openai-api";
  return (
    <article
      aria-label={`Lượt ${turn.agent}`}
      data-run-id={turn.id}
      className="flex gap-3 py-2"
    >
      <div className="shrink-0 pt-1">
        {agent ? (
          <Logo entity={agent} size={32} />
        ) : (
          <span className="flex size-8 items-center justify-center rounded-full bg-stone-100">
            🤖
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <b>{turn.agent.replace(/^@/, "")}</b>
          {running && onStop && (
            <button className="btn btn-light" onClick={onStop}>
              Dừng agent
            </button>
          )}
          <span className="rounded bg-stone-100 px-1 font-mono text-[10px] text-stone-500">
            {turn.model || agent?.model || "Model mặc định"}
          </span>
          <time className="text-[11px] text-stone-400">
            {eventDate(turn.at).toLocaleTimeString("vi-VN", {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </time>
          {turn.endedAt && (
            <span className="text-[10px] text-stone-400">
              {Math.max(
                0,
                (Date.parse(turn.endedAt) - Date.parse(turn.at)) / 1000,
              ).toFixed(1)}
              s
            </span>
          )}
        </div>
        <MarkdownContent
          text={cleanContent(turn.content)}
          agents={agents}
          streaming={running}
        />
        <TurnDetails
          ticketId={ticketId}
          turn={turn}
          running={running}
          api={api}
          onLog={onLog}
        />
        {running && (
          <p className="mt-2 animate-pulse text-xs text-stone-400">
            {turn.agent} đang làm việc <span>● ● ●</span>
          </p>
        )}
        {turn.failed && (
          <p className="text-xs text-red-700">
            Lượt làm việc gặp lỗi; xem log để biết chi tiết.
          </p>
        )}
        {turn.gate?.kind === "human_confirm" && (
          <InlineConfirmBox
            gate={turn.gate}
            active={activeGate}
            canConfirm={canConfirm}
            onConfirm={onConfirm}
          />
        )}
      </div>
    </article>
  );
}
