import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { OrchestratorForm } from "@/components/workflow/OrchestratorForm";

function setup(failPublish = false) {
  const writes: { url: string; body: Record<string, unknown> }[] = [];
  let publishCount = 0;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input);
    if (url.endsWith("effective-agents"))
      return Response.json([
        {
          id: "leader",
          handle: "@leader",
          display_name: "Coordinator",
          role_key: "COORDINATOR",
          is_active: true,
        },
        {
          id: "dev",
          handle: "@developer",
          display_name: "Developer",
          role_key: "DEVELOPER",
          is_active: true,
        },
        {
          id: "disabled",
          handle: "@disabled",
          role_key: "TESTER",
          is_active: false,
        },
      ]);
    writes.push({ url, body: JSON.parse(String(options?.body || "{}")) });
    if (url.endsWith("/publish") && failPublish && publishCount++ === 0)
      return Response.json({ detail: "Publish failed" }, { status: 500 });
    return Response.json({ id: "w1" });
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <OrchestratorForm pid="p1" />
    </QueryClientProvider>,
  );
  return writes;
}

test("create Orchestrator by selecting coordinator and instructions without canvas", async () => {
  const writes = setup();
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByRole("combobox", { name: "Agent điều phối" }),
    "leader",
  );
  expect(
    screen.queryByRole("option", { name: /disabled/ }),
  ).not.toBeInTheDocument();
  await user.type(
    screen.getByRole("textbox", { name: "Instruction" }),
    "Build then verify",
  );
  await user.click(screen.getByRole("button", { name: "Lưu & xuất bản" }));
  await waitFor(() => expect(writes).toHaveLength(2));
  expect(writes[0].url).toBe("/api/backend/projects/p1/workflows");
  expect(writes[0].body.orchestrator).toEqual({
    coordinator_agent_id: "leader",
    instructions: "Build then verify",
    max_rounds: 20,
  });
  expect(writes[1].url).toBe("/api/backend/workflows/w1/publish");
});

test("publish retry reuses the created Orchestrator", async () => {
  const writes = setup(true);
  const user = userEvent.setup();
  await user.selectOptions(
    await screen.findByRole("combobox", { name: "Agent điều phối" }),
    "leader",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Instruction" }),
    "Deliver task",
  );
  await user.click(screen.getByRole("button", { name: "Lưu & xuất bản" }));
  await screen.findByRole("alert");
  await user.click(screen.getByRole("button", { name: "Lưu & xuất bản" }));
  await waitFor(() => expect(writes).toHaveLength(4));
  expect(
    writes.filter((w) => w.url.endsWith("/projects/p1/workflows")),
  ).toHaveLength(1);
  expect(writes[2].url).toBe("/api/backend/workflows/w1/orchestrator");
});
