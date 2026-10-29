import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { DeleteEntityButton } from "@/components/ui-app/delete-entity-button";

function setup(kind: "project" | "workflow" | "ticket", previewFails = false) {
  const fetcher = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (_input, options) => {
      if (!options?.method && previewFails)
        return Response.json(
          { detail: "Không lấy được dữ liệu" },
          { status: 500 },
        );
      return Response.json(
        options?.method === "DELETE"
          ? { ok: true }
          : { workflow_count: 2, ticket_count: 7 },
      );
    });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DeleteEntityButton kind={kind} id="one" name="Example" />
    </QueryClientProvider>,
  );
  return fetcher;
}

test("project deletion lists children and cancel never deletes", async () => {
  const fetcher = setup("project");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Xóa project Example" }));
  expect(await screen.findByText(/2 workflow và 7 ticket/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Huỷ" }));
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("workflow delete sends cascade only after explicit confirmation", async () => {
  const fetcher = setup("workflow");
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "Xóa workflow Example" }),
  );
  expect(
    await screen.findByText(/7 ticket trong workflow/),
  ).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Xác nhận" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(fetcher.mock.calls[1][0]).toBe(
    "/api/backend/workflows/one?cascade=true",
  );
  expect(fetcher.mock.calls[1][1]?.method).toBe("DELETE");
});

test("failed preview does not allow deletion", async () => {
  const fetcher = setup("project", true);
  await userEvent.click(
    screen.getByRole("button", { name: "Xóa project Example" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Xóa project Example" }),
    ).toBeEnabled(),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

test("ticket deletion requires confirmation without requesting child counts", async () => {
  const fetcher = setup("ticket");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Xóa ticket Example" }));
  expect(await screen.findByText(/không thể khôi phục/)).toBeInTheDocument();
  expect(fetcher).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Xác nhận" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  expect(fetcher.mock.calls[0][0]).toBe("/api/backend/tickets/one");
});
