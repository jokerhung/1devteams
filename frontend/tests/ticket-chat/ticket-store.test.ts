import { describe, it, expect } from "vitest";
import fixture from "./fixtures/bugfix-events.json";
import { createTicketStore } from "@/stores/ticket-store";
import type { ChatEvent, MessageGroup } from "@/components/ticket-chat/types";
const events = fixture as ChatEvent[];
describe("ticket replay", () => {
  it("continues a summarized answer without duplicating streamed text and keeps gates resolved", () => {
    const store = createTicketStore();
    const run = "run-summary";
    const summary: MessageGroup = {
      type: "turn",
      id: run,
      agent: "@developer",
      at: events[0].created_at,
      historySeq: 10,
      lastSeq: 20,
      content: "Saved answer",
      thinking: "",
      tools: {},
      files: {},
      terminals: [],
      permissions: [],
      plans: [],
      logLines: [],
      gate: { key: "gate", kind: "human_confirm", payload: {} },
    };
    store.getState().history([summary]);
    store.setState({ afterSeq: 20 });
    const event = {
      ...events[0],
      sender_type: "AGENT",
      sender_name: "@developer",
      run_id: run,
    };
    store.getState().ingest([
      {
        ...event,
        seq: 20,
        event_type: "message_chunk",
        content: "Saved answer",
      },
      { ...event, seq: 21, event_type: "message_chunk", content: " continued" },
      {
        ...event,
        seq: 22,
        run_id: null,
        event_type: "gate_resolved",
        content: "",
        metadata: { gate_key: "gate", approved: true },
      },
    ]);
    const turn = store
      .getState()
      .groups.find((group) => group.type === "turn")!;
    expect(turn.type === "turn" && turn.content).toBe("Saved answer continued");
    expect(turn.type === "turn" && turn.gate?.resolved?.approved).toBe(true);
    expect(summary.type === "turn" && summary.gate?.resolved).toBeUndefined();
    store
      .getState()
      .history([
        {
          type: "system",
          id: "older",
          text: "Older page",
          at: events[0].created_at,
          historySeq: 1,
          lastSeq: 1,
        },
      ]);
    expect(store.getState().groups[0].id).toBe("older");
    expect(store.getState().afterSeq).toBe(22);
    expect(store.getState().groups).toHaveLength(2);
  });
  it("keeps the live cursor when older pages are prepended and recovers live gaps", () => {
    const store = createTicketStore();
    store.setState({ afterSeq: 100, stateSeq: 100, status: "COMPLETED" });
    store.getState().ingest([
      { ...events[0], seq: 90 },
      { ...events[0], seq: 102 },
    ]);
    expect(store.getState().afterSeq).toBe(100);
    store.getState().ingest([{ ...events[0], seq: 101 }]);
    expect(store.getState().afterSeq).toBe(102);
    store.getState().ingest([{ ...events[0], seq: 1 }]);
    expect(store.getState().afterSeq).toBe(102);
    expect(store.getState().events.map((event) => event.seq)).toEqual([
      1, 90, 101, 102,
    ]);
    expect(store.getState().status).toBe("COMPLETED");
  });
  it("deduplicates replay, orders events and resumes only contiguous sequences", () => {
    const store = createTicketStore();
    store.getState().ingest([events[0], events[2], events[2]]);
    expect(store.getState().afterSeq).toBe(1);
    store.getState().ingest([events[1]]);
    expect(store.getState().afterSeq).toBe(3);
    store.getState().ingest(events);
    store.getState().ingest(events);
    expect(store.getState().events).toHaveLength(events.length);
    expect(store.getState().afterSeq).toBe(events.at(-1)!.seq);
  });
  it("does not regress a current snapshot when old history replays", () => {
    const store = createTicketStore();
    store.getState().snapshot({
      status: "COMPLETED",
      current_node_id: null,
      waiting: null,
      node_statuses: {},
      last_seq: events.at(-1)!.seq,
    });
    store.getState().ingest(events.slice(0, 20));
    expect(store.getState().status).toBe("COMPLETED");
    expect(store.getState().waiting).toBeNull();
  });
  it("acknowledges optimistic sends by client message identity", () => {
    const store = createTicketStore();
    store
      .getState()
      .addPending({ id: "client-1", text: "hello", attachments: [] });
    store.getState().failPending("client-1");
    expect(store.getState().pending[0].failed).toBe(true);
    store
      .getState()
      .ingest([{ ...events[0], metadata: { client_msg_id: "client-1" } }]);
    expect(store.getState().pending).toEqual([]);
  });
});
