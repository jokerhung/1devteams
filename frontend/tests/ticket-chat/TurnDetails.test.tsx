import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { TurnDetails } from "@/components/ticket-chat/TurnDetails";
import { groupEvents } from "@/components/ticket-chat/groupEvents";
import fixture from "./fixtures/bugfix-events.json";
import type { ChatEvent, TurnGroup } from "@/components/ticket-chat/types";

const { fetchDetails } = vi.hoisted(() => ({ fetchDetails: vi.fn() }));
vi.mock("@/lib/api", () => ({ apiFetch: fetchDetails }));

it("fetches details only on expansion and reuses cached data on reopening", async () => {
  const events = ["agent_turn_start", "terminal_output", "agent_turn_end"].map(
    (kind, index) => ({
      ...fixture[0],
      id: `detail-${index}`,
      run_id: "run-1",
      sender_type: "AGENT",
      sender_name: "@leader",
      event_type: kind,
      content: kind === "terminal_output" ? "on-demand terminal output" : "",
      seq: index + 1,
      metadata: {},
    }),
  ) as ChatEvent[];
  fetchDetails.mockResolvedValue(events);
  const turn = groupEvents(events).find(
    (group) => group.type === "turn",
  ) as TurnGroup;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <TurnDetails
        ticketId="ticket-1"
        turn={turn}
        running={false}
        api={false}
        onLog={() => {}}
      />
    </QueryClientProvider>,
  );
  expect(fetchDetails).not.toHaveBeenCalled();
  const summary = screen.getByText(
    "Chi tiết lượt trả lời · tool, diff, log, terminal",
  );
  fireEvent.click(summary);
  await waitFor(() => expect(fetchDetails).toHaveBeenCalledOnce());
  expect(fetchDetails.mock.calls[0][0]).toBe(
    "/tickets/ticket-1/turns/run-1/details",
  );
  await screen.findByText("on-demand terminal output");
  fireEvent.click(summary);
  fireEvent.click(summary);
  await screen.findByText("on-demand terminal output");
  expect(fetchDetails).toHaveBeenCalledOnce();
  client.clear();
});
