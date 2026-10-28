import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, test, vi } from "vitest";
import { WorkspaceFiles } from "@/components/ticket-chat/WorkspaceFiles";

afterEach(() => vi.unstubAllGlobals());

test("outside a project, opens allowed folders and browses files within the selected root", async () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  const root = "D:\\allowed";
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname.endsWith("/workspace-file")) {
        expect(url.searchParams.get("root")).toBe(root);
        expect(url.searchParams.get("path")).toBe("notes.txt");
        return Response.json({
          path: "notes.txt",
          content: "Folder contents",
          size: 15,
        });
      }
      expect(url.pathname).toBe("/api/backend/projects/workspace-files");
      expect(url.searchParams.get("path")).toBe("");
      return Response.json({
        path: "",
        truncated: false,
        entries: url.searchParams.get("root")
          ? [{ name: "notes.txt", path: "notes.txt", kind: "file" }]
          : [{ name: root, path: root, kind: "directory" }],
      });
    });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkspaceFiles onClose={() => {}} />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: root }));
  await user.click(await screen.findByRole("button", { name: "notes.txt" }));
  expect(await screen.findByText("Folder contents")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Lên thư mục cha" }));
  expect(await screen.findByRole("button", { name: root })).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByText("Folder contents")).not.toBeInTheDocument(),
  );
  expect(
    fetch.mock.calls.some(([input]) =>
      String(input).includes("/projects/undefined/"),
    ),
  ).toBe(false);
});
