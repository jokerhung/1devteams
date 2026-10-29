import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { CreateWorkflowWizard } from "@/components/workflow/CreateWorkflowWizard";

test("new custom template is available when creating a project workflow", async () => {
  const key = "wf_" + "a".repeat(32);
  const writes: RequestInit[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    const url = String(input);
    if (options?.method === "POST") {
      writes.push(options);
      return Response.json({ id: "created" });
    }
    if (url.includes("workflow-templates"))
      return Response.json([
        { id: key, name: "My template", graph: { nodes: [], edges: [] } },
      ]);
    return Response.json([]);
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CreateWorkflowWizard pid="p1" />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Tiếp tục" }));
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Chọn template" }),
    key,
  );
  await user.click(screen.getByRole("button", { name: "Tiếp tục" }));
  expect(
    screen.getByText("Template: My template", { exact: false }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Tạo & mở canvas" }));
  await waitFor(() => expect(writes).toHaveLength(1));
  expect(JSON.parse(String(writes[0].body)).template).toBe(key);
});
