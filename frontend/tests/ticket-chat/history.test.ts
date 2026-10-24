import { beforeEach, expect, it, vi } from "vitest";
import { loadTicketHistory } from "@/lib/ticket-history";

const { fetchPage } = vi.hoisted(() => ({ fetchPage: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiFetch: fetchPage }));
beforeEach(() => fetchPage.mockReset());

it("loads only one page of ten messages on entry", async () => {
  const page = { groups: [], before_seq: 100, has_more: true, last_seq: 300 };
  fetchPage.mockResolvedValue(page);
  const signal = new AbortController().signal;
  expect(await loadTicketHistory("ticket", signal)).toBe(page);
  expect(fetchPage).toHaveBeenCalledExactlyOnceWith(
    "/tickets/ticket/history?limit=10",
    { signal },
  );
});

it("uses an exclusive older cursor and the original snapshot watermark", async () => {
  await loadTicketHistory("ticket", new AbortController().signal, 100, 300);
  expect(fetchPage.mock.calls[0][0]).toBe(
    "/tickets/ticket/history?limit=10&before_seq=100&through_seq=300",
  );
});

it("does not fetch after navigating away", () => {
  const controller = new AbortController();
  controller.abort();
  expect(() => loadTicketHistory("ticket", controller.signal)).toThrow();
  expect(fetchPage).not.toHaveBeenCalled();
});
