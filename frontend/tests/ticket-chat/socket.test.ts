import { afterEach, expect, it, vi } from "vitest";
import { TicketSocket } from "@/lib/ws";
class Source {
  static instances: Source[] = [];
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  close = vi.fn();
  constructor(public url: string) {
    Source.instances.push(this);
  }
}
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  Source.instances = [];
});
it("batches replay events and flushes before snapshots and reconnects", () => {
  vi.useFakeTimers();
  vi.stubGlobal("EventSource", Source);
  let cursor = 0;
  const events = vi.fn((batch: { seq: number }[]) => {
    cursor = batch.at(-1)!.seq;
  });
  const snapshot = vi.fn(() => expect(cursor).toBe(101));
  const socket = new TicketSocket("ticket", () => cursor, {
    events,
    snapshot,
    connection: vi.fn(),
  });
  socket.connect();
  const emit = (seq: number) =>
    Source.instances[0].onmessage!({
      data: JSON.stringify({ type: "event", data: { seq } }),
    });
  for (let seq = 1; seq <= 100; seq++) emit(seq);
  expect(events).not.toHaveBeenCalled();
  vi.advanceTimersByTime(50);
  expect(events).toHaveBeenCalledOnce();
  expect(events.mock.calls[0][0]).toHaveLength(100);
  emit(101);
  Source.instances[0].onmessage!({
    data: JSON.stringify({ type: "snapshot", state: {} }),
  });
  expect(snapshot).toHaveBeenCalledOnce();
  emit(102);
  Source.instances[0].onerror!();
  vi.advanceTimersByTime(1000);
  expect(Source.instances[1].url).toContain("after_seq=102");
  Source.instances[1].onmessage!({
    data: JSON.stringify({ type: "event", data: { seq: 103 } }),
  });
  socket.close();
  vi.advanceTimersByTime(100);
  expect(cursor).toBe(102);
});
it("reconnects with the current cursor, exponential delays and stops on disposal", () => {
  vi.useFakeTimers();
  vi.stubGlobal("EventSource", Source);
  let cursor = 10;
  const handlers = { connection: vi.fn(), event: vi.fn(), snapshot: vi.fn() };
  const socket = new TicketSocket("ticket", () => cursor, handlers);
  socket.connect();
  expect(Source.instances[0].url).toContain("after_seq=10");
  Source.instances[0].onerror!();
  cursor = 12;
  vi.advanceTimersByTime(1000);
  expect(Source.instances[1].url).toContain("after_seq=12");
  Source.instances[1].onerror!();
  vi.advanceTimersByTime(1999);
  expect(Source.instances).toHaveLength(2);
  vi.advanceTimersByTime(1);
  Source.instances[2].onmessage!({
    data: JSON.stringify({ type: "snapshot", state: { status: "RUNNING" } }),
  });
  expect(handlers.snapshot).toHaveBeenCalledWith({ status: "RUNNING" });
  Source.instances[2].onerror!();
  socket.close();
  vi.advanceTimersByTime(10000);
  expect(Source.instances).toHaveLength(3);
});
