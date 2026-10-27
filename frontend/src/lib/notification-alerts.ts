"use client";

import { toast } from "sonner";

const seen = new Set<string>();

export function alertNewNotification(value: unknown) {
  if (!value || typeof value !== "object") return;
  const notice = value as Record<string, unknown>;
  if (typeof notice.id !== "string" || typeof notice.title !== "string") return;
  const key = `${notice.user_id || ""}:${notice.id}`;
  if (seen.has(key)) return;
  seen.add(key);
  if (seen.size > 500) seen.delete(seen.values().next().value!);
  const body = typeof notice.body === "string" ? notice.body : "";
  const url = ["project_id", "workflow_id", "ticket_id"].every(
    (field) => typeof notice[field] === "string",
  )
    ? `/projects/${encodeURIComponent(String(notice.project_id))}/workflows/${encodeURIComponent(String(notice.workflow_id))}/tickets/${encodeURIComponent(String(notice.ticket_id))}?focus=gate`
    : "/notifications";
  const open = () => {
    window.location.assign(url);
  };
  toast.info(notice.title, {
    id: `notification-${key}`,
    description: body,
    duration: 10000,
    action: { label: "Xem", onClick: open },
  });
  if (
    typeof window.Notification !== "function" ||
    Notification.permission !== "granted"
  )
    return;
  const options: NotificationOptions = {
    body,
    tag: `1teams-${key}`,
    icon: "/brand/aiteams-icon.png",
    data: { url },
  };
  try {
    const notification = new Notification(`1Teams · ${notice.title}`, options);
    notification.onclick = () => {
      window.focus();
      notification.close();
      open();
    };
  } catch {
    // Some mobile browsers require persistent notifications via a service worker.
    if ("serviceWorker" in navigator) {
      void navigator.serviceWorker
        .register("/notification-worker.js")
        .then(() => navigator.serviceWorker.ready)
        .then((registration) =>
          registration.showNotification(`1Teams · ${notice.title}`, options),
        )
        .catch(() => {
          /* The in-app toast remains available. */
        });
    }
  }
}
