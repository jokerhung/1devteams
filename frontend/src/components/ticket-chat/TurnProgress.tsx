"use client";
import { useQuery } from "@tanstack/react-query";
import {
  ActionTimeline,
  type TimelineAction,
} from "@/components/ui-app/action-timeline";
import { apiFetch } from "@/lib/api";
import { groupEvents } from "./groupEvents";
import type { ChatEvent, TurnGroup } from "./types";

export function TurnProgress({
  ticketId,
  turn,
}: {
  ticketId: string;
  turn: TurnGroup;
}) {
  // Backfill actions when opening a ticket mid-turn. Subsequent updates arrive
  // through the ticket socket, including updates to an existing tool call.
  const details = useQuery({
    queryKey: ["ticket", ticketId, "turn-progress", turn.id],
    queryFn: ({ signal }) =>
      apiFetch<ChatEvent[]>(`/tickets/${ticketId}/turns/${turn.id}/details`, {
        signal,
      }),
    staleTime: Infinity,
  });
  const history = groupEvents(details.data || []).find(
    (group): group is TurnGroup =>
      group.type === "turn" && group.id === turn.id,
  );
  const tools = { ...history?.tools };
  for (const [key, tool] of Object.entries(turn.tools)) {
    if (!tools[key] || tool.seq >= tools[key].seq) tools[key] = tool;
  }
  const logs = new Map(
    [...(history?.logLines || []), ...turn.logLines].map((line) => [
      line.seq,
      line,
    ]),
  );
  const toolSequences = new Set(Object.values(tools).map((event) => event.seq));
  const actions = [
    ...Object.entries(tools).map(([id, event]) => ({
      id: `tool-${id}`,
      seq: event.seq,
      kind: (event.metadata.kind === "execute"
        ? "command"
        : undefined) as TimelineAction["kind"],
      title: String(
        event.metadata.title ||
          event.metadata.kind ||
          event.content ||
          "Công cụ",
      ),
      status: String(event.metadata.status || "in_progress"),
    })),
    ...Object.values({ ...history?.files, ...turn.files }).map(
      (file, index) => ({
        id: `file-${file.path}`,
        seq: Math.max(history?.lastSeq || 0, turn.lastSeq || 0) + index / 1000,
        title: file.path,
        status: "completed",
        kind: "file" as const,
        added: file.diff
          .split("\n")
          .filter((line) => line.startsWith("+") && !line.startsWith("+++"))
          .length,
        removed: file.diff
          .split("\n")
          .filter((line) => line.startsWith("-") && !line.startsWith("---"))
          .length,
      }),
    ),
    ...[...logs.values()]
      .filter(
        (line) =>
          !["tool", "think"].includes(line.kind) &&
          !toolSequences.has(line.seq),
      )
      .map((line) => ({
        id: `log-${line.seq}`,
        seq: line.seq,
        title: line.text,
        status: ["error", "deny"].includes(line.kind) ? "failed" : "completed",
      })),
  ].sort((a, b) => a.seq - b.seq);

  return (
    <ActionTimeline
      actions={actions}
      startedAt={Date.parse(turn.at)}
      label={`${turn.agent} đang làm việc…`}
    />
  );
}
