"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { groupEvents } from "./groupEvents";
import type { ChatEvent, TurnGroup } from "./types";
import { AgentLog } from "./AgentLog";
import { FileDiffBlock } from "./blocks/FileDiffBlock";
import {
  ThinkingBlock,
  ToolCallChips,
  PlanBlock,
  TerminalBlock,
  PermissionLog,
} from "./blocks/RuntimeBlocks";

export function TurnDetails({
  ticketId,
  turn,
  running,
  api,
  onLog,
}: {
  ticketId: string;
  turn: TurnGroup;
  running: boolean;
  api: boolean;
  onLog: () => void;
}) {
  const [open, setOpen] = useState(false);
  const details = useQuery({
    queryKey: [
      "ticket",
      ticketId,
      "turn-details",
      turn.id,
      turn.endedAt || "live",
    ],
    queryFn: ({ signal }) =>
      apiFetch<ChatEvent[]>(`/tickets/${ticketId}/turns/${turn.id}/details`, {
        signal,
      }),
    enabled: open,
    staleTime: Infinity,
    refetchInterval: open && running ? 3000 : false,
  });
  const full = useMemo(
    () =>
      groupEvents(details.data || []).find(
        (group) => group.type === "turn" && group.id === turn.id,
      ) as TurnGroup | undefined,
    [details.data, turn.id],
  );
  return (
    <details
      className="my-2 rounded-lg border border-stone-200 p-3 text-xs"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-stone-600">
        Chi tiết lượt trả lời · tool, diff, log, terminal
      </summary>
      {open && (
        <div className="mt-2">
          {details.isPending && <p role="status">Đang tải chi tiết…</p>}
          {details.error && (
            <div role="alert">
              <p>{details.error.message}</p>
              <button
                className="underline"
                onClick={() => void details.refetch()}
              >
                Thử lại
              </button>
            </div>
          )}
          {full && (
            <>
              <AgentLog
                lines={full.logLines}
                running={running}
                onFull={onLog}
              />
              {full.fullOutputs?.map((url) => (
                <a
                  key={url}
                  href={url.replace("/api/", "/api/backend/")}
                  className="my-2 block underline"
                  download
                >
                  Tải output đầy đủ
                </a>
              ))}
              <ThinkingBlock text={full.thinking} running={running} />
              {!api && <ToolCallChips tools={Object.values(full.tools)} />}
              {full.plans.map((event) => (
                <PlanBlock key={event.id} event={event} />
              ))}
              {!api && (
                <>
                  {Object.values(full.files).map((file) => (
                    <FileDiffBlock key={file.path} change={file} />
                  ))}
                  {full.terminals.map((event) => (
                    <TerminalBlock key={event.id} event={event} />
                  ))}
                  {full.permissions.map((event) => (
                    <PermissionLog
                      key={event.id}
                      event={event}
                      agent={turn.agent}
                    />
                  ))}
                </>
              )}
            </>
          )}
          {details.isSuccess && !full && <p>Không có chi tiết cho lượt này.</p>}
        </div>
      )}
    </details>
  );
}
