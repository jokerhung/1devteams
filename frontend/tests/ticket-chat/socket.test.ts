import { afterEach, expect, it, vi } from "vitest";
import { TicketSocket } from "@/lib/ws";
class Source {
  static instances: Source[] = [];
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  close = vi.fn();
  constructor(public url: string) { Source.instances.push(this); }
}
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); Source.instances = []; });
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
  Source.instances[2].onmessage!({ data: JSON.stringify({ type: "snapshot", state: { status: "RUNNING" } }) });
  expect(handlers.snapshot).toHaveBeenCalledWith({ status: "RUNNING" });
  Source.instances[2].onerror!();
  socket.close();
  vi.advanceTimersByTime(10000);
  expect(Source.instances).toHaveLength(3);
});
