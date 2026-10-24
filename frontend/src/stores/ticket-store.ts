import { createStore } from "zustand/vanilla";
import { groupEvents } from "@/components/ticket-chat/groupEvents";
import type {
  ChatEvent,
  MessageGroup,
  PendingMessage,
  RuntimeState,
} from "@/components/ticket-chat/types";
type Store = RuntimeState & {
  events: ChatEvent[];
  groups: MessageGroup[];
  summaries: MessageGroup[];
  history: (groups: MessageGroup[]) => void;
  pending: PendingMessage[];
  afterSeq: number;
  stateSeq: number;
  connection: "connecting" | "connected" | "reconnecting";
  ingest: (events: ChatEvent[]) => void;
  snapshot: (state: RuntimeState) => void;
  addPending: (message: PendingMessage) => void;
  failPending: (id: string) => void;
};
export function createTicketStore(status = "OPEN") {
  return createStore<Store>()((set) => ({
    events: [],
    groups: [],
    summaries: [],
    history: (incoming) =>
      set((s) => {
        const byId = new Map(s.summaries.map((group) => [group.id, group]));
        incoming.forEach((group) => byId.set(group.id, group));
        const summaries = [...byId.values()].sort(
          (a, b) => (a.historySeq ?? 0) - (b.historySeq ?? 0),
        );
        return { summaries, groups: groupEvents(s.events, summaries) };
      }),
    pending: [],
    afterSeq: 0,
    stateSeq: 0,
    status,
    waiting: null,
    node_statuses: {},
    current_node_id: null,
    connection: "connecting",
    snapshot: (state) =>
      set((s) =>
        (state.last_seq ?? 0) < s.stateSeq
          ? {}
          : { ...state, stateSeq: state.last_seq ?? s.stateSeq },
      ),
    addPending: (message) =>
      set((s) => ({
        pending: [...s.pending.filter((m) => m.id !== message.id), message],
      })),
    failPending: (id) =>
      set((s) => ({
        pending: s.pending.map((m) =>
          m.id === id ? { ...m, failed: true } : m,
        ),
      })),
    ingest: (incoming) =>
      set((s) => {
        const bySeq = new Map(s.events.map((e) => [e.seq, e]));
        incoming.forEach((e) => bySeq.set(e.seq, e));
        const events = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
        const next = {
          result: s.result,
          status: s.status,
          waiting: s.waiting,
          current_node_id: s.current_node_id,
          node_statuses: { ...s.node_statuses },
          stateSeq: s.stateSeq,
        };
        for (const e of events) {
          if (e.seq <= s.stateSeq) continue;
          const m = e.metadata || {};
          if (e.event_type === "ticket_status") {
            if (m.result) next.result = m.result as Record<string, unknown>;
            next.status = String(m.status);
            next.current_node_id = m.current_node_id as string | null;
            if (!next.status.startsWith("WAITING")) next.waiting = null;
            if (next.current_node_id)
              next.node_statuses[next.current_node_id] =
                next.status === "FAILED"
                  ? "failed"
                  : next.status.startsWith("WAITING")
                    ? "waiting"
                    : next.status === "RUNNING"
                      ? "running"
                      : "done";
          }
          if (e.event_type === "gate_waiting")
            next.waiting = {
              kind: String(m.kind),
              node_id: e.node_id!,
              payload: m,
            };
          if (e.event_type === "gate_resolved") next.waiting = null;
          if (
            e.node_id &&
            ["agent_turn_start", "agent_turn_end"].includes(e.event_type)
          )
            next.node_statuses[e.node_id] =
              e.event_type === "agent_turn_start" ? "running" : "done";
          next.stateSeq = e.seq;
        }
        const ids = new Set(
          events.flatMap((e) => [
            e.id,
            String(e.metadata?.client_msg_id || ""),
          ]),
        );
        let afterSeq = s.afterSeq;
        for (const event of events) {
          if (event.seq <= afterSeq) continue;
          if (event.seq !== afterSeq + 1) break;
          afterSeq = event.seq;
        }
        return {
          ...next,
          events,
          groups: groupEvents(events, s.summaries),
          afterSeq,
          pending: s.pending.filter((m) => !ids.has(m.id)),
        };
      }),
  }));
}
export type TicketStore = ReturnType<typeof createTicketStore>;
