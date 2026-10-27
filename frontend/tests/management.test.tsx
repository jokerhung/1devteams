import { render, screen, waitFor, within, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import { vi, test, expect } from "vitest";
import { toast } from "sonner";
import { AgentForm } from "@/components/ui-app/agent-form";
import { LogoPicker } from "@/components/ui-app/primitives";
import { Sidebar, recentProjects } from "@/components/ui-app/sidebar";
import { WorkspaceToolsProvider } from "@/components/ui-app/workspace-tools";
import { TeamForm } from "@/components/ui-app/team-form";
import NotificationsPage from "@/app/(workspace)/notifications/page";
import { useRealtime } from "@/lib/realtime";
import { apiFetch } from "@/lib/api";
import type { Agent, Project, Notice } from "@/lib/types";
const agent: Agent = {
  id: "a1",
  handle: "@ba",
  display_name: "BA",
  role_key: "BA",
  description: null,
  runtime: "claude-code",
  base_url: null,
  model: null,
  fallback_model: null,
  has_key: false,
  api_key_last4: null,
  api_params: {},
  system_prompt: "",
  icon: "🐝",
  logo_url: null,
  color: "sky",
  is_builtin: true,
  is_active: true,
  config_version: 1,
  restarted_at: null,
  created_at: "",
  updated_at: "",
  permission_profile: {
    allow_read: true,
    allow_write: false,
    allow_terminal: false,
    allow_fetch: false,
    allow_browser: false,
    can_git_release: false,
    allowed_commands: [],
    blocked_commands: [],
  },
};
function mount(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return {
    client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}
function mockApi(
  overrides: (path: string, init?: RequestInit) => unknown = () => undefined,
) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const path = String(input);
      if (path.endsWith("/agents/native-options")) {
        const { runtime } = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            models:
              runtime === "codex"
                ? [{ id: "codex-model", label: "Codex Model" }]
                : [{ id: "sonnet", label: "Sonnet" }],
            reasoning_levels: [],
          }),
          { status: 200 },
        );
      }
      const overridden = overrides(path, init);
      const data =
        overridden ??
        (path.includes("models-catalog")
          ? {
              "claude-code": [{ id: "sonnet", label: "Sonnet" }],
              codex: [{ id: "codex-model", label: "Codex Model" }],
            }
          : path.includes("/usage")
            ? { running_tickets: [{ id: "t1" }] }
            : path.includes("permission-presets")
              ? { read_only: agent.permission_profile }
              : []);
      return new Response(JSON.stringify(data), { status: 200 });
    });
}
test("AgentForm changes native models and enforces API text-only permissions and required key", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  mount(<AgentForm teams={[]} onClose={vi.fn()} onRestart={vi.fn()} />);
  await screen.findByRole("option", { name: "Sonnet" });
  await user.selectOptions(screen.getByLabelText("Loại Agent"), "codex");
  expect(
    screen.getByRole("option", { name: "Codex Model" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: "Sonnet" }),
  ).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("Loại Agent"), "openai-api");
  expect(screen.queryByLabelText("Model ACP")).not.toBeInTheDocument();
  expect(
    screen.getByRole("option", { name: "Đọc/Ghi không commit" }),
  ).toBeDisabled();
  expect(screen.getByLabelText("API Key")).toBeRequired();
  expect(screen.getByLabelText("Base URL")).toBeRequired();
  await user.type(screen.getByLabelText("Tên Agent (Handle)"), "INVALID!");
  expect(screen.getByText(/Handle không hợp lệ/)).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Tên Agent (Handle)"));
  await user.type(screen.getByLabelText("Tên Agent (Handle)"), "@review");
  await user.type(screen.getByLabelText("Vai trò"), "Reviewer");
  await user.type(screen.getByLabelText("Base URL"), "https://example.com/v1");
  await user.type(screen.getByLabelText("Model", { exact: true }), "gpt-5");
  await user.click(screen.getByRole("button", { name: "Lưu Agent" }));
  expect(
    fetch.mock.calls.filter(
      ([input, init]) =>
        String(input).endsWith("/agents") && init?.method === "POST",
    ),
  ).toHaveLength(0);
});
test("editing unchanged agent locks handle, warns about active usage and avoids PATCH/restart", async () => {
  const fetch = mockApi();
  const restart = vi.fn();
  const close = vi.fn();
  const user = userEvent.setup();
  mount(
    <AgentForm agent={agent} teams={[]} onClose={close} onRestart={restart} />,
  );
  expect(screen.getByLabelText("Tên Agent (Handle)")).toBeDisabled();
  await screen.findByText(/1 ticket/);
  expect(screen.getByText(/Lưu thay đổi sẽ khởi động lại/)).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Lưu & khởi động lại" }));
  await waitFor(() => expect(close).toHaveBeenCalled());
  expect(restart).not.toHaveBeenCalled();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
    false,
  );
});
test("editing API agent with blank key omits key, tests stored connection and saves other changes", async () => {
  const custom = {
    ...agent,
    runtime: "openai-api" as const,
    base_url: "https://example.com/v1",
    has_key: true,
    model: "gpt-5",
  };
  const fetch = mockApi((path, init) =>
    path.endsWith("/test-connection")
      ? { ok: true, status: 200, latency_ms: 128, models: [] }
      : init?.method === "PATCH"
        ? { agent: custom, restart: true }
        : undefined,
  );
  const user = userEvent.setup();
  mount(
    <AgentForm
      agent={custom}
      teams={[]}
      onClose={vi.fn()}
      onRestart={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("API Key")).not.toBeRequired();
  await user.click(screen.getByRole("button", { name: "Kiểm tra kết nối" }));
  await screen.findByText(/GET \/models 200 · 128 ms/);
  await user.type(screen.getByLabelText("Vai trò"), " updated");
  await user.click(screen.getByRole("button", { name: "Lưu & khởi động lại" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
      true,
    ),
  );
  const call = fetch.mock.calls.find(([, init]) => init?.method === "PATCH")!;
  expect(JSON.parse(String(call[1]?.body))).not.toHaveProperty("api_key");
});
test("LogoPicker selects emoji and refuses oversized uploads before network", async () => {
  const fetch = mockApi();
  const onChange = vi.fn();
  const user = userEvent.setup();
  mount(<LogoPicker icon="🤖" logo_url={null} onChange={onChange} />);
  await user.click(screen.getByRole("button", { name: "Logo 🛡️" }));
  expect(onChange).toHaveBeenCalledWith("🛡️", null);
  const file = new File([new Uint8Array(300 * 1024 + 1)], "large.png", {
    type: "image/png",
  });
  await user.upload(screen.getByLabelText("Tải logo"), file);
  expect(toast.error).toHaveBeenCalledWith("Logo tối đa 300KB");
  expect(fetch).not.toHaveBeenCalled();
});
test("TeamForm cannot save empty team", () => {
  mockApi();
  mount(<TeamForm agents={[agent]} onClose={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Lưu AI Team" })).toBeDisabled();
  expect(
    screen.getByText("AI Team phải có ít nhất 1 agent."),
  ).toBeInTheDocument();
});
const projects = Array.from(
  { length: 6 },
  (_, i) =>
    ({
      id: `p${i + 1}`,
      name: `Project ${i + 1}`,
      workspace_path: "/tmp/work",
      default_branch: "main",
      last_activity_at: `2026-10-${String(i + 10).padStart(2, "0")}T00:00:00Z`,
    }) as Project,
);
test("recent project pin replaces slot five without mutating activity order", () => {
  expect(recentProjects(projects, "p1").map((p) => p.id)).toEqual([
    "p6",
    "p5",
    "p4",
    "p3",
    "p1",
  ]);
  expect(projects[0].id).toBe("p1");
});
test("Sidebar keeps projects independently expanded, name clicks preserve order, and shows all modal", async () => {
  mockApi((path) =>
    path.includes("/projects?")
      ? { items: projects, total: 6 }
      : path.endsWith("/tree")
        ? { workflows: [] }
        : path.endsWith("/auth/me")
          ? { display_name: "Owner" }
          : path.endsWith("/health")
            ? { acp: { claude: true, codex: true } }
            : path.endsWith("unread-count")
              ? { open: 2 }
              : undefined,
  );
  const user = userEvent.setup();
  mount(
    <WorkspaceToolsProvider>
      <Sidebar />
    </WorkspaceToolsProvider>,
  );
  await screen.findByRole("link", { name: "Project 6" });
  const agentChat = screen.getByRole("button", { name: "Chat với AI Agent" });
  expect(agentChat).toHaveAttribute("aria-pressed", "false");
  await user.click(agentChat);
  expect(agentChat).toHaveAttribute("aria-pressed", "true");
  await user.click(
    screen.getByRole("button", { name: "Mở project Project 6" }),
  );
  await user.click(
    screen.getByRole("button", { name: "Mở project Project 5" }),
  );
  expect(localStorage.getItem("sidebar.open.p6")).toBe("true");
  expect(localStorage.getItem("sidebar.open.p5")).toBe("true");
  const before = screen
    .getAllByTestId("sidebar-project")
    .map((e) => e.textContent);
  screen
    .getByRole("link", { name: "Project 6" })
    .addEventListener("click", (e) => e.preventDefault());
  await user.click(screen.getByRole("link", { name: "Project 6" }));
  expect(
    screen.getAllByTestId("sidebar-project").map((e) => e.textContent),
  ).toEqual(before);
  await user.click(
    screen.getByRole("button", { name: "Thu gọn project Project 6" }),
  );
  expect(localStorage.getItem("sidebar.open.p6")).toBe("false");
  expect(localStorage.getItem("sidebar.open.p5")).toBe("true");
  await user.click(screen.getByRole("button", { name: "Xem tất cả (6)" }));
  expect(within(screen.getByRole("dialog")).getAllByRole("link")).toHaveLength(
    7,
  );
});
test("notifications and sidebar count refetch when backend resolves notification", async () => {
  let resolved = false;
  let onmessage: ((event: { data: string }) => void) | null = null;
  vi.stubGlobal(
    "EventSource",
    class {
      set onmessage(fn: (event: { data: string }) => void) {
        onmessage = fn;
      }
      close() {}
    },
  );
  const notice = {
    id: "n1",
    title: "Duyệt sửa lỗi",
    body: "Vui lòng xác nhận",
    type: "CONFIRM",
    project_id: "p1",
    workflow_id: "w1",
    ticket_id: "t1",
    project: { name: "Project" },
    workflow: { name: "Fix Bug" },
    ticket: { code: "#BUG-1", title: "Bug" },
    created_at: new Date().toISOString(),
    outcome: "APPROVED",
  } as Notice;
  mockApi((path) =>
    path.includes("/notifications?")
      ? {
          items: (path.includes("status=resolved") ? resolved : !resolved)
            ? [notice]
            : [],
          total: (path.includes("status=resolved") ? resolved : !resolved)
            ? 1
            : 0,
        }
      : path.endsWith("/notifications/unread-count")
        ? { open: resolved ? 0 : 1 }
        : undefined,
  );
  function Harness() {
    useRealtime("users/me");
    const count = useQuery({
      queryKey: ["notifications", "count"],
      queryFn: () => apiFetch<{ open: number }>("/notifications/unread-count"),
    });
    return (
      <>
        <output aria-label="Badge cần xử lý">{count.data?.open}</output>
        <NotificationsPage />
      </>
    );
  }
  const user = userEvent.setup();
  mount(<Harness />);
  await screen.findByText("Duyệt sửa lỗi");
  expect(screen.getByLabelText("Badge cần xử lý")).toHaveTextContent("1");
  resolved = true;
  await act(async () => {
    onmessage!({
      data: JSON.stringify({
        channel: "users/me",
        event_type: "notification_resolved",
      }),
    });
  });
  await screen.findByText("Không có gì cần xử lý 🎉");
  await waitFor(() =>
    expect(screen.getByLabelText("Badge cần xử lý")).toHaveTextContent("0"),
  );
  await user.click(screen.getByRole("tab", { name: /Đã xử lý/ }));
  await screen.findByText("✓ Đã xác nhận");
});

test("API draft connection uses entered key and exposes discovered models and errors", async () => {
  let ok = true;
  const fetch = mockApi((path) =>
    path.endsWith("/test-connection-draft") || path.endsWith("/api-options")
      ? {
          ok,
          status: ok ? 200 : 401,
          latency_ms: 128,
          models: [{ id: "custom-model" }],
          error: ok ? null : "API key không hợp lệ",
        }
      : undefined,
  );
  const user = userEvent.setup();
  mount(<AgentForm teams={[]} onClose={vi.fn()} onRestart={vi.fn()} />);
  await user.selectOptions(screen.getByLabelText("Loại Agent"), "openai-api");
  await user.type(screen.getByLabelText("Base URL"), "invalid");
  expect(
    screen.getByText("Base URL không hợp lệ (cần http:// hoặc https://)"),
  ).toBeInTheDocument();
  await user.clear(screen.getByLabelText("Base URL"));
  await user.type(screen.getByLabelText("Base URL"), "https://example.com/v1/");
  await user.type(screen.getByLabelText("API Key"), "test-only-key");
  await user.type(screen.getByLabelText("Model", { exact: true }), "gpt-5");
  await user.click(screen.getByRole("button", { name: "Kiểm tra kết nối" }));
  await screen.findByText(/GET \/models 200 · 128 ms/);
  await user.click(screen.getByRole("button", { name: "Tải model từ API" }));
  await waitFor(() =>
    expect(
      document.querySelector('option[value="custom-model"]'),
    ).toBeInTheDocument(),
  );
  expect(
    document.querySelector('option[value="custom-model"]'),
  ).toBeInTheDocument();
  const call = fetch.mock.calls.find(([url]) =>
    String(url).endsWith("/test-connection-draft"),
  )!;
  expect(JSON.parse(String(call[1]?.body))).toEqual({
    base_url: "https://example.com/v1",
    api_key: "test-only-key",
    model: "gpt-5",
  });
  ok = false;
  await user.click(screen.getByRole("button", { name: "Kiểm tra kết nối" }));
  await screen.findByText("✘ API key không hợp lệ");
});

test("removing sole agent from a team is refused before saving configuration", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  const restart = vi.fn();
  mount(
    <AgentForm
      agent={agent}
      teams={[
        {
          id: "team1",
          name: "Solo Team",
          description: "",
          icon: "🐝",
          logo_url: null,
          agent_ids: ["a1"],
          created_at: "",
          updated_at: "",
        },
      ]}
      onClose={vi.fn()}
      onRestart={restart}
    />,
  );
  await user.click(screen.getByRole("checkbox", { name: /Solo Team/ }));
  await user.click(screen.getByRole("button", { name: "Lưu & khởi động lại" }));
  expect(screen.getByRole("alert")).toHaveTextContent("là agent duy nhất");
  expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
    false,
  );
  expect(restart).not.toHaveBeenCalled();
});
