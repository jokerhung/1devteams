import { createPatch } from "diff";
import type {
  ChatEvent,
  Gate,
  LogLine,
  MessageGroup,
  TurnGroup,
  BrowserReport,
} from "./types";
export function toLogLine(e: ChatEvent): LogLine | null {
  const m = e.metadata || {};
  const type = e.event_type;
  let kind: LogLine["kind"] = "info";
  if (type === "permission") kind = m.allowed === false ? "deny" : "perm";
  else if (type.startsWith("tool_call"))
    kind = m.status === "failed" ? "error" : "tool";
  else if (type === "thought_chunk") kind = "think";
  else if (type === "error") kind = "error";
  else if (type === "log" && /✔|finish_reason|tokens:/.test(e.content))
    kind = "ok";
  else if (
    !["log", "plan", "agent_turn_start", "agent_turn_end"].includes(type)
  )
    return null;
  const detail =
    type === "permission"
      ? `permission: ${m.action || m.command || "tool"} → ${m.allowed === false ? "DENY" : "ALLOW"} (${m.reason || e.content})`
      : type.startsWith("tool_call")
        ? `tool: ${m.title || m.kind || e.content || "tool"} (${m.status || "pending"})`
        : type === "agent_turn_start"
          ? "→ Bắt đầu lượt làm việc"
          : type === "agent_turn_end"
            ? "✔ Kết thúc lượt"
            : e.content || JSON.stringify(m);
  return {
    seq: e.seq,
    at: e.created_at,
    agent: e.sender_name,
    kind,
    text: detail.replace(/\s+/g, " ").slice(0, 2000),
  };
}
export function cleanContent(text: string) {
  return text
    .replace(/@@RELEASE[\s\S]*?(?:@@END|$)/g, "")
    .replace(/@@ROUTE:[^\n]*/g, "")
    .trim();
}
export function groupEvents(
  events: ChatEvent[],
  summaries: MessageGroup[] = [],
): MessageGroup[] {
  const groups: MessageGroup[] = structuredClone(summaries);
  const turns = new Map<string, TurnGroup>();
  const gates = new Map<string, Gate>();
  const bases = new Map(summaries.map((group) => [group.id, group]));
  for (const group of groups) {
    if (group.type === "turn") {
      turns.set(group.id, group);
      if (group.gate) gates.set(group.gate.key, group.gate);
    }
  }
  let latest: TurnGroup | undefined = [...turns.values()].at(-1);
  for (const e of events) {
    const base = bases.get(e.run_id || e.id);
    if (base && e.seq <= (base.lastSeq ?? 0)) continue;
    if (e.sender_type === "USER") {
      groups.push({
        type: "user",
        id: e.id,
        event: e,
        historySeq: e.seq,
        lastSeq: e.seq,
      });
      continue;
    }
    const m = e.metadata || {};
    if (e.event_type === "gate_waiting") {
      const gate: Gate = {
        key: String(m.gate_key || e.id),
        kind: String(m.kind),
        payload: m,
      };
      gates.set(gate.key, gate);
      if (latest) latest.gate = gate;
      continue;
    }
    if (e.event_type === "gate_resolved") {
      const gate = gates.get(String(m.gate_key));
      if (gate)
        gate.resolved = {
          approved: m.approved as boolean | undefined,
          user: m.user as { display_name?: string },
          at: e.created_at,
        };
      if (m.approved === false)
        groups.push({
          type: "system",
          id: e.id,
          text:
            "🔄 Luồng đã quay lại @developer — " +
            String(m.feedback || "Yêu cầu sửa lại"),
          at: e.created_at,
          historySeq: e.seq,
          lastSeq: e.seq,
        });
      continue;
    }
    if (e.event_type === "ticket_status") continue;
    if (e.run_id && (e.sender_type === "AGENT" || turns.has(e.run_id))) {
      let turn = turns.get(e.run_id);
      if (!turn) {
        turn = {
          type: "turn",
          id: e.run_id,
          agent: e.sender_name,
          nodeId: e.node_id,
          at: e.created_at,
          content: "",
          thinking: "",
          tools: {},
          files: {},
          terminals: [],
          permissions: [],
          plans: [],
          logLines: [],
          historySeq: e.seq,
          lastSeq: e.seq,
          detailsAvailable: true,
        };
        turns.set(e.run_id, turn);
        groups.push(turn);
      }
      latest = turn;
      turn.lastSeq = e.seq;
      if (
        typeof m.full_output_url === "string" &&
        /^\/api\/tickets\/[\w-]+\/event-blobs\/[\w-]+$/.test(m.full_output_url)
      ) {
        turn.fullOutputs = [...(turn.fullOutputs || []), m.full_output_url];
      }
      if (m.model_effective || m.model)
        turn.model = String(m.model_effective || m.model);
      if (m.runtime) turn.runtime = String(m.runtime);
      const line = toLogLine(e);
      if (line) turn.logLines.push(line);
      switch (e.event_type) {
        case "browser_report":
          turn.browserReports = [
            ...(turn.browserReports || []),
            m as BrowserReport,
          ];
          break;
        case "message_chunk":
          turn.content += e.content;
          break;
        case "thought_chunk":
          turn.thinking += e.content;
          break;
        case "agent_turn_end":
          turn.content = e.content;
          turn.endedAt = e.created_at;
          break;
        case "error":
          turn.failed = true;
          break;
        case "tool_call":
        case "tool_call_update": {
          const key = String(m.tool_call_id || m.toolCallId || m.id || e.id);
          const previous = turn.tools[key];
          turn.tools[key] = {
            ...e,
            content: e.content || previous?.content || "",
            metadata: { ...previous?.metadata, ...m },
          };
          break;
        }
        case "file_edit": {
          const path = String(m.path || m.file || "file");
          const old = turn.files[path]?.old ?? String(m.old_text || "");
          const next = String(m.new_text || "");
          turn.files[path] = {
            path,
            old,
            next,
            diff: "",
          };
          break;
        }
        case "terminal_output": {
          const terminalId = m.terminal_id || m.terminalId || m.tool_call_id;
          const previous = terminalId
            ? turn.terminals.find(
                (item) =>
                  (item.metadata.terminal_id ||
                    item.metadata.terminalId ||
                    item.metadata.tool_call_id) === terminalId,
              )
            : undefined;
          if (previous) {
            previous.content += e.content;
            previous.metadata = { ...previous.metadata, ...m };
          } else {
            turn.terminals.push({ ...e, metadata: { ...m } });
          }
          break;
        }
        case "permission":
          if (m.allowed === false) turn.permissions.push(e);
          break;
        case "plan":
          turn.plans.push(e);
          break;
      }
    } else if (
      e.event_type === "error" ||
      (e.event_type === "log" && e.content)
    ) {
      groups.push({
        type: "system",
        id: e.id,
        text: e.content,
        at: e.created_at,
        historySeq: e.seq,
        lastSeq: e.seq,
      });
    }
  }
  for (const turn of turns.values()) {
    for (const file of Object.values(turn.files))
      file.diff = createPatch(file.path, file.old, file.next);
  }
  return groups.sort((a, b) => (a.historySeq ?? 0) - (b.historySeq ?? 0));
}
