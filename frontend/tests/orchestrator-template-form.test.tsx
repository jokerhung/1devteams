import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { OrchestratorTemplateForm } from "@/components/workflow/OrchestratorTemplateForm";

test("create portable template with role definitions and optional markdown document", async () => {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_input, options) =>
      Response.json(
        options?.method === "POST"
          ? { id: "new-template" }
          : [
              {
                id: "leader",
                handle: "@leader",
                display_name: "Leader",
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
                id: "design",
                handle: "@designer",
                display_name: "Designer",
                role_key: "DESIGNER",
                is_active: true,
              },
              {
                id: "inactive",
                handle: "@inactive",
                display_name: "Inactive",
                role_key: "TESTER",
                is_active: false,
              },
            ],
      ),
    );
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={new QueryClient()}>
      <OrchestratorTemplateForm />
    </QueryClientProvider>,
  );
  await user.type(
    await screen.findByRole("textbox", { name: "Tên template" }),
    "New team",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Instruction của Orchestrator" }),
    "Ask before proceeding",
  );
  await user.click(screen.getByRole("button", { name: "Thêm thành viên" }));
  expect(
    screen.queryByRole("textbox", { name: /Vai trò|Handle/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: /@inactive/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Agent điều phối" })).toHaveValue(
    "leader",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Agent thực hiện 2" }),
    "design",
  );
  await user.type(
    screen.getAllByRole("textbox", {
      name: "File Markdown đầu ra (tùy chọn)",
    })[1],
    "design.md",
  );
  await user.click(screen.getByRole("button", { name: "Lưu template" }));
  await waitFor(() =>
    expect(
      fetcher.mock.calls.filter(([, options]) => options?.method === "POST"),
    ).toHaveLength(1),
  );
  const [url, options] = fetcher.mock.calls.find(
    ([, options]) => options?.method === "POST",
  )!;
  expect(url).toBe("/api/backend/orchestrator-templates");
  expect(options?.method).toBe("POST");
  expect(JSON.parse(String(options?.body))).toMatchObject({
    name: "New team",
    coordinator_role: "COORDINATOR",
    coordinator_handle: "@leader",
    workers: [
      { role_key: "DEVELOPER" },
      {
        role_key: "DESIGNER",
        agent_handle: "@designer",
        document_name: "design.md",
      },
    ],
  });
});
