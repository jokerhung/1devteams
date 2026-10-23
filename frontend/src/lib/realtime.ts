"use client";
import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
export function useRealtime(channel: string, enabled = true) {
  const client = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    // The server bridges authenticated backend WebSockets; the httpOnly JWT stays on the server.
    const source = new EventSource(
      `/api/events?channel=${encodeURIComponent(channel)}`,
    );
    source.onmessage = ({ data }) => {
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
    };
    return () => source.close();
  }, [channel, client, enabled]);
}
