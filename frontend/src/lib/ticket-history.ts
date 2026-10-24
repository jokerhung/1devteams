import { apiFetch } from "./api";
import type { components } from "@/lib/api/schema";
import type { MessageGroup } from "@/components/ticket-chat/types";

export type HistoryPage = Omit<
  components["schemas"]["HistoryOut"],
  "groups"
> & { groups: MessageGroup[] };

export function loadTicketHistory(
  tid: string,
  signal: AbortSignal,
  before?: number,
  through?: number,
) {
  signal.throwIfAborted();
  const query = new URLSearchParams({ limit: "10" });
  if (before != null) query.set("before_seq", String(before));
  if (through != null) query.set("through_seq", String(through));
  return apiFetch<HistoryPage>(`/tickets/${tid}/history?${query}`, { signal });
}
