import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { CreateWorkflowTemplateDialog } from "@/components/workflow/CreateWorkflowTemplateDialog";

const templates = [
  { id: "blank", name: "Trống" },
  { id: "add_feature", name: "Add feature" },
];

test("creates named Workflow template from selected source", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(Response.json({ id: "wf_new" }));
  const close = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CreateWorkflowTemplateDialog templates={templates} onClose={close} />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  expect(
    screen.getByRole("button", { name: "Tạo template" }),
  ).toBeDisabled();
  await user.type(
    screen.getByRole("textbox", { name: "Tên template" }),
    "New workflow template",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Bắt đầu từ" }),
    "add_feature",
  );
  await user.click(
    screen.getByRole("button", { name: "Tạo template" }),
  );
  await waitFor(() => expect(close).toHaveBeenCalledOnce());
  expect(fetcher.mock.calls[0][0]).toBe("/api/backend/workflow-templates");
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({
    name: "New workflow template",
    description: "",
    source_template: "add_feature",
  });
});

test("creation error keeps entered values and dialog available", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({ detail: "Không thể tạo template" }, { status: 422 }),
  );
  const close = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CreateWorkflowTemplateDialog templates={templates} onClose={close} />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.type(
    screen.getByRole("textbox", { name: "Tên template" }),
    "Retry me",
  );
  await user.click(
    screen.getByRole("button", { name: "Tạo template" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Không thể tạo template",
  );
  expect(screen.getByRole("textbox", { name: "Tên template" })).toHaveValue(
    "Retry me",
  );
  expect(close).not.toHaveBeenCalled();
});
