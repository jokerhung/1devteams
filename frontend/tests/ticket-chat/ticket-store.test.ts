import { describe, it, expect } from "vitest";
import fixture from "./fixtures/bugfix-events.json";
import { createTicketStore } from "@/stores/ticket-store";
import type { ChatEvent } from "@/components/ticket-chat/types";
const events = fixture as ChatEvent[];
describe("ticket replay", () => {
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
    store
      .getState()
      .snapshot({
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
