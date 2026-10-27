import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { TurnProgress } from "@/components/ticket-chat/TurnProgress";
import { groupEvents } from "@/components/ticket-chat/groupEvents";
import type { ChatEvent, TurnGroup } from "@/components/ticket-chat/types";
import fixture from "./fixtures/bugfix-events.json";

const { fetchDetails } = vi.hoisted(() => ({ fetchDetails: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiFetch: fetchDetails }));

it("backfills five recent actions and applies live tool updates without duplicate rows", async () => {
  const events = Array.from({ length: 7 }, (_, index) => ({
    ...fixture[0],
    id: `event-${index}`,
    run_id: "run-1",
    sender_type: "AGENT",
    sender_name: "@tester",
    seq: index + 1,
    event_type: "tool_call",
    content: `Action ${index}`,
    metadata: { tool_call_id: `tool-${index}`, status: "in_progress" },
  })) as ChatEvent[];
  fetchDetails.mockResolvedValue(events);
  const turn = groupEvents([events[6]])[0] as TurnGroup;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = (value: TurnGroup) => (
    <QueryClientProvider client={client}>
      <TurnProgress ticketId="ticket-1" turn={value} />
    </QueryClientProvider>
  );
  const { rerender, unmount } = render(view(turn));
  const list = await screen.findByRole("list", {
    name: "5 hành động gần nhất",
  });
  await screen.findByText("Action 2");
  expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  expect(within(list).queryByText("Action 1")).not.toBeInTheDocument();
  expect(within(list).getAllByLabelText("Đang chạy")).toHaveLength(5);
  const update = {
    ...events[6],
    id: "update",
    seq: 8,
    event_type: "tool_call_update",
    metadata: { tool_call_id: "tool-6", status: "completed" },
  };
  rerender(view(groupEvents([events[6], update])[0] as TurnGroup));
  expect(within(list).getAllByRole("listitem")).toHaveLength(5);
  expect(within(list).getByLabelText("Hoàn tất")).toBeInTheDocument();
  expect(screen.getByLabelText("Đang xử lý")).toHaveClass("animate-spin");
  rerender(
    view(
      groupEvents([
        {
          ...update,
          seq: 9,
          metadata: { ...update.metadata, status: "failed" },
        },
      ])[0] as TurnGroup,
    ),
  );
  expect(within(list).getByLabelText("Lỗi")).toBeInTheDocument();
  unmount();
  client.clear();
});
