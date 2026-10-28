import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import {
  WorkspaceToolsArea,
  WorkspaceToolsProvider,
  useWorkspaceTools,
} from "@/components/ui-app/workspace-tools";

const route = vi.hoisted(() => ({ pathname: "/agents" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
vi.mock("@/components/ui-app/agent-chat", () => ({ AgentChat: () => null }));
vi.mock("@/components/ticket-chat/WorkspaceFiles", () => ({
  WorkspaceFiles: () => null,
}));
vi.mock("@/components/ticket-chat/TerminalDock", () => ({
  TerminalDock: ({
    projectId,
    workspace,
    open,
    created,
    children,
  }: {
    projectId?: string;
    workspace?: string;
    open: boolean;
    created: boolean;
    children: React.ReactNode;
  }) => (
    <>
      {open && created && (
        <div data-testid="terminal-target">{projectId || workspace}</div>
      )}
      {children}
    </>
  ),
}));

function Toggle() {
  const tools = useWorkspaceTools();
  return <button onClick={tools.toggleTerminal}>Terminal</button>;
}

function Harness() {
  return (
    <WorkspaceToolsProvider>
      <Toggle />
      <WorkspaceToolsArea>Page</WorkspaceToolsArea>
    </WorkspaceToolsProvider>
  );
}

it("defaults to the first allowed folder outside projects, ignoring a previously selected project", async () => {
  route.pathname = "/agents";
  localStorage.setItem("lastProjectId", "previous-project");
  const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({
      enabled: true,
      workspace: "/allowed/first",
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Terminal" }));
  expect(await screen.findByTestId("terminal-target")).toHaveTextContent(
    "/allowed/first",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/backend/workspace-terminal",
    expect.anything(),
  );
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});

it.each([
  "/projects/p1",
  "/projects/p1/workflows/w1",
  "/projects/p1/workflows/w1/tickets/t1",
  "/projects/p1/settings",
])(
  "uses the routed project for %s, then switches to the default folder on an unrelated menu",
  async (pathname) => {
    route.pathname = pathname;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      Response.json({
        enabled: true,
        workspace: "/allowed/first",
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Terminal" }));
    expect(await screen.findByTestId("terminal-target")).toHaveTextContent(
      "p1",
    );
    expect(fetch).not.toHaveBeenCalled();
    route.pathname = "/settings/adapters";
    rerender(
      <QueryClientProvider client={client}>
        <Harness />
      </QueryClientProvider>,
    );
    await waitFor(() =>
      expect(screen.getByTestId("terminal-target")).toHaveTextContent(
        "/allowed/first",
      ),
    );
  },
);

it("reports an unavailable default workspace without starting a terminal", async () => {
  route.pathname = "/projects";
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    Response.json({ detail: "Chưa cấu hình thư mục" }, { status: 400 }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Terminal" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Chưa cấu hình thư mục",
  );
  expect(screen.queryByTestId("terminal-target")).not.toBeInTheDocument();
});
