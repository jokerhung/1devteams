import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { AgentChat } from "@/components/ui-app/agent-chat";

function mount() {
  vi.spyOn(HTMLElement.prototype, "scrollIntoView").mockImplementation(
    () => {},
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AgentChat open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

function mockApi(failFirst = false, stream?: ReadableStream<Uint8Array>) {
  const requests: {
    agent_id: string;
    project_id: string | null;
    messages: { role: string; content: string }[];
  }[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, options) => {
    if (String(input).includes("/projects?"))
      return Response.json({ items: [{ id: "p1", name: "Project One" }], total: 1 });
    if (String(input).endsWith("/agents"))
      return Response.json([
        {
          id: "a1",
          model: "model-one",
          display_name: "One",
          handle: "@one",
          runtime: "openai-api",
          is_active: true,
        },
        {
          id: "a2",
          model: "model-two",
          display_name: "Two",
          handle: "@two",
          runtime: "codex",
          is_active: true,
        },
        { id: "a3", model: "disabled", is_active: false },
      ]);
    expect(String(input)).toBe("/api/backend/agent-chat");
    requests.push(JSON.parse(String(options?.body)));
    if (stream)
      return new Response(stream, {
        headers: { "Content-Type": "text/event-stream" },
      });
    if (failFirst && requests.length === 1)
      return Response.json({ detail: "Agent tạm thời lỗi" }, { status: 502 });
    return Response.json({
      message: "Xin chào Nam",
      reports: [
        {
          test_case: "Login",
          status: "PASS",
          summary: "Trang đăng nhập đã được kiểm tra",
          url: "http://localhost/dashboard",
          checks: [{ action: "assert_visible" }],
          screenshot: "data:image/png;base64,iVBORw0KGgo=",
        },
      ],
    });
  });
  return requests;
}

test("direct chat sends context, separates agent conversations and can start fresh", async () => {
  HTMLElement.prototype.scrollIntoView = () => {};
  const requests = mockApi();
  const user = userEvent.setup();
  mount();
  const selector = await screen.findByRole("combobox", {
    name: "AI Agent",
  });
  await waitFor(() => expect(selector).toHaveValue("a1"));
  expect(
    screen.getByRole("option", { name: "One (@one)" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("option", { name: "Two (@two)" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("option", { name: /disabled/ }),
  ).not.toBeInTheDocument();
  const input = screen.getByRole("textbox", { name: "Tin nhắn cho AI Agent" });
  await user.type(input, "Tôi là Nam");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  await screen.findByText("Xin chào Nam");
  expect(
    screen.getByRole("region", { name: "Kết quả test Login" }),
  ).toHaveTextContent("PASS · Login");
  expect(screen.getByRole("img", { name: "Screenshot Login" })).toHaveAttribute(
    "src",
    "data:image/png;base64,iVBORw0KGgo=",
  );
  await user.click(
    screen.getByRole("button", { name: "Phóng to Screenshot Login" }),
  );
  const preview = await screen.findByRole("dialog", {
    name: "Screenshot Login",
  });
  expect(
    within(preview).getByRole("img", {
      name: "Ảnh phóng to: Screenshot Login",
    }),
  ).toHaveAttribute("src", "data:image/png;base64,iVBORw0KGgo=");
  const download = within(preview).getByRole("link", { name: "Tải ảnh xuống" });
  expect(download).toHaveAttribute("download", "screenshot.png");
  expect(download).toHaveAttribute(
    "href",
    "data:image/png;base64,iVBORw0KGgo=",
  );
  await user.click(
    within(preview).getByRole("button", { name: "Đóng ảnh phóng to" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  await user.click(
    screen.getByRole("button", { name: "Phóng to Screenshot Login" }),
  );
  await screen.findByRole("dialog", { name: "Screenshot Login" });
  await user.keyboard("{Escape}");
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  await user.type(input, "Tên tôi là gì?");
  await user.keyboard("{Control>}{Enter}{/Control}");
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1]).toEqual({
    agent_id: "a1",
    project_id: null,
    messages: [
      { role: "user", content: "Tôi là Nam" },
      { role: "assistant", content: "Xin chào Nam" },
      { role: "user", content: "Tên tôi là gì?" },
    ],
  });
  await waitFor(() => expect(selector).toBeEnabled());
  await user.selectOptions(selector, "a2");
  expect(screen.queryByText("Tôi là Nam")).not.toBeInTheDocument();
  await user.selectOptions(selector, "a1");
  expect(screen.getByText("Tôi là Nam")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Cuộc trò chuyện mới" }));
  expect(screen.queryByText("Tôi là Nam")).not.toBeInTheDocument();
});

test("project is optional and conversations stay separate when switching project", async () => {
  const requests = mockApi();
  const user = userEvent.setup();
  mount();
  const selector = await screen.findByRole("combobox", { name: "Project" });
  await waitFor(() => expect(selector).toBeEnabled());
  expect(selector).toHaveValue("");
  const input = screen.getByRole("textbox", { name: "Tin nhắn cho AI Agent" });
  await user.type(input, "Không có project");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  await screen.findByText("Xin chào Nam");
  expect(requests[0].project_id).toBeNull();
  await user.selectOptions(selector, "p1");
  expect(screen.queryByText("Xin chào Nam")).not.toBeInTheDocument();
  await user.type(input, "Kiểm tra project");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  await screen.findByText("Xin chào Nam");
  expect(requests[1].project_id).toBe("p1");
  expect(requests[1].messages).toEqual([
    { role: "user", content: "Kiểm tra project" },
  ]);
  await user.selectOptions(selector, "");
  expect(screen.getByText("Không có project")).toBeInTheDocument();
});

test("failed chat restores draft and retry sends the user message once", async () => {
  HTMLElement.prototype.scrollIntoView = () => {};
  const requests = mockApi(true);
  const user = userEvent.setup();
  mount();
  const input = screen.getByRole("textbox", { name: "Tin nhắn cho AI Agent" });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Xin chào");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Agent tạm thời lỗi",
  );
  expect(input).toHaveValue("Xin chào");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  await screen.findByText("Xin chào Nam");
  expect(requests[1].messages).toEqual([{ role: "user", content: "Xin chào" }]);
});

test("shows only the last five live actions and loading until the final reply", async () => {
  HTMLElement.prototype.scrollIntoView = () => {};
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value;
    },
  });
  mockApi(false, stream);
  const user = userEvent.setup();
  mount();
  const input = screen.getByRole("textbox", { name: "Tin nhắn cho AI Agent" });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "Test website");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  expect(screen.getByLabelText("Đang xử lý")).toHaveClass("animate-spin");
  const encoder = new TextEncoder();
  await act(async () => {
    controller.enqueue(encoder.encode(": keepalive\n\n"));
    for (let i = 1; i <= 7; i++) {
      const bytes = encoder.encode(
        `data: ${JSON.stringify({ type: "action", id: String(i), title: `Hành động ${i}`, status: "in_progress" })}\n\n`,
      );
      // Frames and Vietnamese UTF-8 characters may cross transport chunks.
      for (let offset = 0; offset < bytes.length; offset += 3)
        controller.enqueue(bytes.slice(offset, offset + 3));
    }
  });
  const logs = await screen.findByRole("list", {
    name: "5 hành động gần nhất",
  });
  expect(within(logs).getAllByRole("listitem")).toHaveLength(5);
  expect(logs).not.toHaveTextContent("Hành động 1");
  expect(logs).not.toHaveTextContent("Hành động 2");
  expect(logs).toHaveTextContent("Hành động 7");
  await act(async () => {
    controller.enqueue(
      encoder.encode(
        `data: ${JSON.stringify({ type: "action", id: "7", title: "Đã hoàn tất hành động 7", status: "completed" })}\n\n`,
      ),
    );
  });
  expect(within(logs).getAllByRole("listitem")).toHaveLength(5);
  expect(logs).toHaveTextContent("Đã hoàn tất hành động 7");
  expect(screen.getByLabelText("Đang xử lý")).toBeInTheDocument();
  await act(async () => {
    controller.enqueue(
      encoder.encode(
        `data: ${JSON.stringify({ type: "reply", message: "Đã kiểm tra xong", reports: [] })}\n\n`,
      ),
    );
    controller.close();
  });
  expect(await screen.findByText("Đã kiểm tra xong")).toBeInTheDocument();
  expect(screen.queryByLabelText("Đang xử lý")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("list", { name: "5 hành động gần nhất" }),
  ).not.toBeInTheDocument();
});
