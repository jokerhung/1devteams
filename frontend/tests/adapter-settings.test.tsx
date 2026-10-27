import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import AdaptersPage from "@/app/(workspace)/settings/adapters/page";

function mount() {
  let current: Record<string, unknown> | null = null;
  const fetch = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/settings/adapters"))
        return Response.json({
          "codex-acp": { installed: false, version: null },
          codex: { installed: true, version: "1.0" },
          claude: { installed: true, version: "2.0" },
        });
      if (url.endsWith("/settings/adapter-actions"))
        return Response.json(current);
      if (url.endsWith("/actions")) {
        const body = JSON.parse(String(init?.body));
        current = {
          id: "job1",
          adapter: url.split("/").at(-2),
          action: body.action,
          status: body.action === "login" ? "running" : "completed",
          output:
            body.action === "login"
              ? "Open provider login"
              : "Installed successfully",
          exit_code: 0,
        };
        return Response.json(current, { status: 202 });
      }
      if (url.endsWith("/cancel")) {
        current = { ...current, status: "cancelled" };
        return Response.json(current);
      }
      if (url.endsWith("/input")) return Response.json({ ok: true });
      throw new Error(`Unexpected request: ${url}`);
    });
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const result = render(
    <QueryClientProvider client={client}>
      <AdaptersPage />
    </QueryClientProvider>,
  );
  return {
    fetch,
    close: () => {
      result.unmount();
      client.clear();
    },
  };
}

it("shows install/login/update with availability and reports completed installation", async () => {
  const { fetch, close } = mount();
  const user = userEvent.setup();
  expect(
    await screen.findByRole("columnheader", { name: "Action" }),
  ).toBeInTheDocument();
  const install = await screen.findByRole("button", {
    name: "Install codex-acp",
  });
  expect(install).toBeEnabled();
  expect(
    screen.getByRole("button", { name: "Update codex-acp" }),
  ).toBeDisabled();
  expect(screen.getByRole("button", { name: "Install codex" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Login codex-acp" })).toBeEnabled();
  await user.click(install);
  expect(await screen.findByText("Installed successfully")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Hoàn tất");
  expect(
    fetch.mock.calls.some(
      ([url, options]) =>
        String(url).endsWith("/codex-acp/actions") &&
        options?.body === JSON.stringify({ action: "install" }),
    ),
  ).toBe(true);
  close();
});

it("shows login instructions, sends the verification code and can cancel the job", async () => {
  const { fetch, close } = mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Login claude" }));
  await screen.findByText("Open provider login");
  expect(screen.getByRole("button", { name: "Update codex" })).toBeDisabled();
  const input = screen.getByLabelText("Mã xác thực CLI");
  await user.type(input, "verification-code");
  await user.click(screen.getByRole("button", { name: "Gửi mã" }));
  await waitFor(() => expect(input).toHaveValue(""));
  expect(
    fetch.mock.calls.some(
      ([url, options]) =>
        String(url).endsWith("/job1/input") &&
        JSON.parse(String(options?.body)).code === "verification-code",
    ),
  ).toBe(true);
  await user.click(screen.getByRole("button", { name: "Dừng" }));
  await waitFor(() =>
    expect(screen.getByRole("status")).toHaveTextContent("Đã dừng"),
  );
  close();
});
