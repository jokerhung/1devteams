import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { toast } from "sonner";
import { alertNewNotification } from "@/lib/notification-alerts";
import { useRealtime } from "@/lib/realtime";
import { BrowserNotifications } from "@/components/ui-app/browser-notifications";

let permission: NotificationPermission;
const native = vi.fn();
const requestPermission = vi.fn();
let onmessage: ((event: { data: string }) => void) | null;

beforeEach(() => {
  permission = "granted";
  native.mockReset();
  requestPermission.mockReset();
  vi.mocked(toast.info).mockClear();
  onmessage = null;
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal(
    "Notification",
    class {
      static get permission() {
        return permission;
      }
      static requestPermission = requestPermission;
      constructor(title: string, options: NotificationOptions) {
        native(title, options);
      }
    },
  );
  vi.stubGlobal(
    "EventSource",
    class {
      set onmessage(handler: (event: { data: string }) => void) {
        onmessage = handler;
      }
      close() {}
    },
  );
});
afterEach(() => vi.unstubAllGlobals());

const notice = (id: string) => ({
  id,
  user_id: "u1",
  title: "Cần xác nhận",
  body: "Tester đã hoàn tất",
  project_id: "p1",
  workflow_id: "w1",
  ticket_id: "t1",
});

test("new user events show both alerts once even with multiple realtime subscribers", async () => {
  function Harness() {
    useRealtime("users/me");
    useRealtime("users/me");
    return null;
  }
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  await act(async () => {
    const data = JSON.stringify({
      channel: "users/me",
      type: "event",
      data: {
        event_type: "notification_created",
        notification: notice("live-1"),
      },
    });
    onmessage!({ data });
    onmessage!({ data });
    onmessage!({
      data: JSON.stringify({
        channel: "users/me",
        event_type: "notification_resolved",
        id: "live-1",
      }),
    });
    onmessage!({
      data: JSON.stringify({
        channel: "users/me",
        type: "snapshot",
        data: { notification: notice("old") },
      }),
    });
  });
  expect(toast.info).toHaveBeenCalledTimes(1);
  expect(toast.info).toHaveBeenCalledWith(
    "Cần xác nhận",
    expect.objectContaining({
      description: "Tester đã hoàn tất",
      action: { label: "Xem", onClick: expect.any(Function) },
    }),
  );
  expect(native).toHaveBeenCalledTimes(1);
  expect(native).toHaveBeenCalledWith(
    "1devTeams · Cần xác nhận",
    expect.objectContaining({
      body: "Tester đã hoàn tất",
      data: { url: "/projects/p1/workflows/w1/tickets/t1?focus=gate" },
    }),
  );
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ["notifications"] });
});

test("toast works when browser permission is denied or unavailable", () => {
  permission = "denied";
  alertNewNotification(notice("denied-1"));
  expect(toast.info).toHaveBeenCalledTimes(1);
  expect(native).not.toHaveBeenCalled();
  vi.stubGlobal("Notification", undefined);
  alertNewNotification(notice("unsupported-1"));
  expect(toast.info).toHaveBeenCalledTimes(2);
  expect(native).not.toHaveBeenCalled();
});

test("permission is requested only when the user clicks enable", async () => {
  permission = "default";
  requestPermission.mockImplementation(async () => {
    permission = "granted";
    return permission;
  });
  const user = userEvent.setup();
  render(<BrowserNotifications />);
  expect(requestPermission).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Bật thông báo trình duyệt" }),
  );
  expect(requestPermission).toHaveBeenCalledOnce();
  expect(screen.getByText(/Đã bật thông báo trình duyệt/)).toBeInTheDocument();
});

test("insecure pages explain how to enable browser notifications", () => {
  vi.stubGlobal("isSecureContext", false);
  render(<BrowserNotifications />);
  expect(screen.getByText(/HTTPS hoặc localhost/)).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Bật thông báo trình duyệt" }),
  ).not.toBeInTheDocument();
  expect(requestPermission).not.toHaveBeenCalled();
});
