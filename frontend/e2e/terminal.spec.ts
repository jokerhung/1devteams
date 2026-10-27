import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("Windows terminal: real output, resize, reconnect, audit and maintainer authorization", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.addInitScript(() => {
    const Original = window.WebSocket;
    const received: string[] = [];
    const sockets: WebSocket[] = [];
    const frames: { type: string; reset?: boolean; seq?: number }[] = [];
    Object.assign(window, {
      terminalFrames: received,
      terminalSockets: sockets,
      terminalEvents: frames,
    });
    window.WebSocket = class extends Original {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols);
        if (!String(url).includes("/ws/terminal/")) return;
        sockets.push(this);
        this.addEventListener("message", (event) => {
          const frame = JSON.parse(event.data);
          frames.push(frame);
          if (frame.type === "output") received.push(frame.data);
        });
      }
    };
  });
  await page.request.post("/api/auth/login", {
    data: { email: "owner@example.com", password: "test-password-123" },
  });
  const runtime = JSON.parse(
    readFileSync(path.resolve(".e2e-data/runtime.json"), "utf8"),
  );
  const project = await (
    await page.request.post("/api/backend/projects", {
      data: {
        name: "Phase 7 terminal",
        workspace_path: runtime.workspace,
        default_branch: "develop",
      },
    })
  ).json();
  const { workflow } = await (
    await page.request.post(`/api/backend/projects/${project.id}/seed-default`)
  ).json();
  const { ticket } = await (
    await page.request.post(`/api/backend/workflows/${workflow.id}/tickets`, {
      data: { title: "Inspect terminal", auto_start: false },
    })
  ).json();
  await page.goto(
    `/projects/${project.id}/workflows/${workflow.id}/tickets/${ticket.id}`,
  );
  await page.getByTestId("ticket-channel").waitFor();
  await page
    .getByRole("button", { name: "Xem workflow của ticket", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Terminal", exact: true })
    .click();
  const terminal = page.getByRole("region", { name: "Remote terminal" });
  await expect(terminal.getByTestId("remote-terminal")).toHaveAttribute(
    "data-connected",
    "true",
  );
  const id = await page
    .getByTestId("remote-terminal")
    .getAttribute("data-session-id");
  expect(id).toBeTruthy();
  await terminal.locator(".xterm-helper-textarea").focus();
  await page.keyboard.type("git status");
  await page.keyboard.press("Enter");
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as unknown as { terminalFrames: string[] }).terminalFrames.join(
          "",
        ),
      ),
    )
    .toContain("On branch develop");
  // Keep PowerShell producing output after the socket closes; reconnect must
  // fetch only the missing sequence range without resetting the current screen.
  await page.evaluate(() => {
    const state = window as unknown as { terminalSockets: WebSocket[] };
    const socket = state.terminalSockets.at(-1)!;
    socket.send(
      JSON.stringify({
        type: "input",
        data: "Start-Sleep -Milliseconds 800; Write-Output ('MISSED_'+'OUTPUT')\r",
      }),
    );
    socket.close();
  });
  await expect
    .poll(() =>
      page.evaluate(() => {
        const state = window as unknown as {
          terminalEvents: { type: string; reset?: boolean }[];
        };
        return state.terminalEvents.filter((f) => f.type === "ready").at(-1)
          ?.reset;
      }),
    )
    .toBe(false);
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as unknown as { terminalFrames: string[] }).terminalFrames.join(
          "",
        ),
      ),
    )
    .toContain("MISSED_OUTPUT");
  await page.setViewportSize({ width: 1100, height: 800 });
  await terminal
    .getByRole("button", { name: "Kết nối lại terminal", exact: true })
    .click();
  await expect(terminal.getByTestId("remote-terminal")).toHaveAttribute(
    "data-connected",
    "true",
  );
  await expect(page.getByTestId("remote-terminal")).toHaveAttribute(
    "data-session-id",
    id!,
  );
  await page.goto("/settings/audit");
  await expect(
    page.getByRole("heading", { name: "Nhật ký hoạt động" }),
  ).toBeVisible();
  await expect(
    page.getByRole("cell", { name: "terminal.open", exact: true }).first(),
  ).toBeVisible();
  const email = `terminal-viewer-${Date.now()}@example.com`;
  const viewer = await (
    await page.request.post("/api/backend/users", {
      data: {
        email,
        display_name: "Terminal Viewer",
        password: "ViewerPassword123!",
        system_role: "MEMBER",
      },
    })
  ).json();
  expect(
    (
      await page.request.post(`/api/backend/projects/${project.id}/members`, {
        data: {
          member_type: "USER",
          member_id: viewer.id,
          project_role: "VIEWER",
        },
      })
    ).ok(),
  ).toBe(true);
  await page.request.post("/api/auth/login", {
    data: { email, password: "ViewerPassword123!" },
  });
  expect(
    (
      await page.request.get(`/api/backend/projects/${project.id}/terminal`)
    ).status(),
  ).toBe(403);
  expect((await page.request.get("/api/backend/audit")).status()).toBe(403);
});
