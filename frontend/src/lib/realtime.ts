"use client";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
// Share sidebar channels within each tab to leave HTTP connections available for actions.
const subscribers = new Map<string, Set<(event: MessageEvent) => void>>();
let sidebarSource: EventSource | undefined;
function reconnectSidebar() {
  sidebarSource?.close();
  if (!subscribers.size) {
    sidebarSource = undefined;
    return;
  }
  sidebarSource = new EventSource(
    `/api/events?channel=${encodeURIComponent([...subscribers.keys()].join(","))}`,
  );
  sidebarSource.onmessage = (event) => {
    try {
      const channel = JSON.parse(event.data).channel;
      for (const handler of subscribers.get(channel) || []) handler(event);
    } catch {
      /* Invalid frames are recovered by reconnect/refetch. */
    }
  };
}
function subscribe(channel: string, handler: (event: MessageEvent) => void) {
  const handlers = subscribers.get(channel) || new Set();
  const added = !subscribers.has(channel);
  handlers.add(handler);
  subscribers.set(channel, handlers);
  if (added) reconnectSidebar();
  return () => {
    handlers.delete(handler);
    if (!handlers.size) {
      subscribers.delete(channel);
      reconnectSidebar();
    }
  };
}
export function useRealtime(channel: string, enabled = true) {
  const client = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    // The server bridges authenticated backend WebSockets; the httpOnly JWT stays on the server.
    return subscribe(channel, ({ data }) => {
      try {
        const frame = JSON.parse(data);
        const event =
          frame.type === "event"
            ? frame.data
            : frame.type === "snapshot"
              ? { event_type: "connected" }
              : frame;
        if (event.event_type?.startsWith("notification_"))
          client.invalidateQueries({ queryKey: ["notifications"] });
        if (event.event_type === "agent_restarted") {
          client.invalidateQueries({ queryKey: ["agents"] });
          window.dispatchEvent(
            new CustomEvent("agent-restarted", { detail: event }),
          );
          toast.success(`${event.agent_handle || "Agent"} đã khởi động lại`);
        }
        if (
          ["ticket_created", "ticket_status", "connected"].includes(
            event.event_type,
          )
        ) {
          client.invalidateQueries({ queryKey: ["projects"] });
          client.invalidateQueries({ queryKey: ["tickets"] });
          client.invalidateQueries({ queryKey: ["notifications"] });
        }
      } catch {
        /* Ignore malformed frames; reconnect/refetch recovers state. */
      }
    });
  }, [channel, client, enabled]);
}
