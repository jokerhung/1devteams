import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import WorkspaceSettingsPage from "@/app/(workspace)/settings/workspaces/page";

test("edits allowed folders, saves without restart and preserves draft on errors", async () => {
  let roots = ["D:\\"];
  let rejected = false;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, options) => {
    if (options?.method === "PUT") {
      if (rejected)
        return Response.json(
          { detail: "Thư mục không tồn tại" },
          { status: 422 },
        );
      roots = JSON.parse(String(options.body)).roots;
    }
    return Response.json({ roots });
  });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkspaceSettingsPage />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  expect(await screen.findByRole("textbox", { name: "Thư mục 1" })).toHaveValue(
    "D:\\",
  );
  await user.click(screen.getByRole("button", { name: "Thêm thư mục" }));
  const extra = screen.getByRole("textbox", { name: "Thư mục 2" });
  await user.type(extra, "C:\\hungnm\\artemis");
  await user.click(screen.getByRole("button", { name: "Lưu cấu hình" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Đã lưu và áp dụng",
  );
  expect(roots).toEqual(["D:\\", "C:\\hungnm\\artemis"]);
  rejected = true;
  await user.clear(extra);
  await user.type(extra, "C:\\missing");
  await user.click(screen.getByRole("button", { name: "Lưu cấu hình" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Thư mục không tồn tại",
  );
  expect(extra).toHaveValue("C:\\missing");
  rejected = false;
  await user.click(screen.getByRole("button", { name: "Xóa thư mục 2" }));
  await user.click(screen.getByRole("button", { name: "Lưu cấu hình" }));
  await waitFor(() => expect(roots).toEqual(["D:\\"]));
});
