import { test, expect } from "@playwright/test";
import path from "node:path";
test("real backend: manage agents, teams, empty projects, members, published workflow and ticket routes", async ({
  page,
}) => {
  test.setTimeout(180000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Mật khẩu").fill("test-password-123");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  const cookies = await page.context().cookies();
  expect(cookies.find((c) => c.name === "aiteams_session")?.httpOnly).toBe(
    true,
  );
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "aiteams_session",
  );
  await page.getByRole("link", { name: /Agents & Teams/ }).click();
  await page.getByRole("button", { name: "Sửa @ba", exact: true }).waitFor();
  await expect(
    page.getByRole("button", { name: "Xoá @ba", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Tạo Agent", exact: true }).click();
  let dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Logo 🛡️", exact: true }).click();
  await dialog.getByLabel("Tên Agent (Handle)").fill("@security_checker");
  await dialog.getByLabel("Vai trò", { exact: true }).fill("Security Checker");
  await dialog.getByLabel("Loại Agent").selectOption("codex");
  await dialog.getByLabel("Model ACP").selectOption({ index: 1 });
  await dialog.getByRole("button", { name: "Lưu Agent", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("@security_checker", { exact: true }),
  ).toBeVisible();
  // Hold only the response to expose the in-flight restart state; the real PATCH executes unchanged.
  await page.route("**/api/backend/agents/*", async (route) => {
    if (route.request().method() === "PATCH") {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 600));
      await route.fulfill({ response });
    } else await route.continue();
  });
  await page
    .getByRole("button", { name: "Sửa @security_checker", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await expect(dialog.getByLabel("Tên Agent (Handle)")).toBeDisabled();
  await expect(dialog.getByText(/Lưu thay đổi sẽ khởi động lại/)).toBeVisible();
  await dialog.getByLabel("Vai trò", { exact: true }).fill("Security Reviewer");
  await dialog.getByRole("button", { name: "Lưu & khởi động lại" }).click();
  await expect(
    page.getByText("↻ Đang khởi động lại…", { exact: true }),
  ).toBeVisible();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByText("Security Reviewer", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("↻ Đang khởi động lại…", { exact: true }),
  ).toHaveCount(0);
  await page.unrouteAll({ behavior: "wait" });
  await page.getByRole("button", { name: "Tạo AI Team", exact: true }).click();
  dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", { name: "Lưu AI Team" }),
  ).toBeDisabled();
  await dialog.getByLabel("Tên AI Team", { exact: true }).fill("Security Team");
  await dialog.getByRole("checkbox", { name: "@security_checker" }).check();
  await dialog.getByRole("button", { name: "Lưu AI Team" }).click();
  await expect(dialog).toHaveCount(0);
  await page.getByRole("button", { name: "Tạo project mới" }).click();
  dialog = page.getByRole("dialog");
  await expect(dialog.locator("input")).toHaveCount(3);
  await expect(dialog.getByText("1. Project")).toHaveCount(0);
  await dialog
    .getByLabel("Tên project", { exact: true })
    .fill("Phase 4 Project");
  await dialog
    .getByRole("button", { name: "Chọn thư mục local", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: path.resolve(".e2e-data"), exact: true })
    .click();
  await dialog.getByRole("button", { name: "workspace", exact: true }).click();
  await dialog
    .getByRole("button", { name: "Chọn thư mục này", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Đường dẫn thư mục local (ACP Working Directory)"),
  ).toHaveValue(path.resolve(".e2e-data/workspace"));
  await dialog.getByLabel("Nhánh Git").click();
  await expect(dialog.getByText("✔ Git repo", { exact: true })).toBeVisible();
  await expect(dialog.getByLabel("Nhánh Git", { exact: true })).toHaveValue(
    "develop",
  );
  await dialog
    .getByRole("button", { name: "Tạo project", exact: true })
    .click();
  await expect(page).toHaveURL(/\/projects\/[a-f0-9-]+$/);
  const projectUrl = page.url();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText(/Chưa có agent nào — hãy thêm AI Team/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Tạo ticket", exact: true }),
  ).toHaveCount(0);
  const pid = projectUrl.split("/").pop()!;
  const emptyMembers = await (
    await page.request.get(`/api/backend/projects/${pid}/members`)
  ).json();
  expect(emptyMembers).toEqual({ users: [], agents: [], teams: [] });
  await page.getByRole("link", { name: "Thành viên & AI Team" }).click();
  await page.getByRole("checkbox", { name: /Core Bugfix Squad/ }).check();
  await expect(
    page.getByRole("checkbox", { name: /Core Bugfix Squad/ }),
  ).toBeEnabled();
  await expect(
    page.getByRole("heading", { name: "Agent hiệu lực trong project" }),
  ).toBeVisible();
  const userResponse = await page.request.post("/api/backend/users", {
    data: {
      email: "reporter@example.com",
      display_name: "Reporter Test",
      password: "test-password-123",
    },
  });
  expect(userResponse.ok()).toBe(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page
    .getByRole("combobox", { name: "Người dùng", exact: true })
    .selectOption({ label: "Reporter Test · reporter@example.com" });
  await page.getByRole("button", { name: "Thêm", exact: true }).click();
  await expect(
    page.getByText("reporter@example.com", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Quyền Reporter Test").selectOption("REPORTER");
  await expect(page.getByLabel("Quyền Reporter Test")).toHaveValue("REPORTER");
  await page.getByRole("link", { name: "Về project", exact: true }).click();
  await page.getByRole("link", { name: "Tạo workflow", exact: true }).click();
  await page.getByRole("button", { name: "Tạo workflow nháp" }).click();
  await expect(
    page.getByRole("button", { name: "+ Tạo ticket", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Xuất bản workflow" }).click();
  await expect(
    page.getByRole("button", { name: "+ Tạo ticket", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Tạo ticket Fix Bug", exact: true })
    .click();
  dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Tiêu đề", { exact: true })
    .fill("Verify management flow");
  await dialog.getByLabel("Mô tả lỗi/yêu cầu").fill("Browser test ticket");
  await dialog.getByLabel("Chỉ tạo, chưa chạy").check();
  await dialog.getByRole("button", { name: "Tạo & mở chat" }).click();
  await expect(page).toHaveURL(/\/workflows\/[a-f0-9-]+\/tickets\/[a-f0-9-]+$/);
  await expect(page.getByText(/Cửa sổ chat đầy đủ/)).toBeVisible();
  await page
    .getByRole("button", { name: "Mở workflow Fix Bug", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: /# bug-verify-management-flow/ }),
  ).toBeVisible();
  // Removing a team required by a published graph must retain the membership and list the workflow.
  await page.goto(`${projectUrl}/members`);
  await page.getByRole("checkbox", { name: /Core Bugfix Squad/ }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Fix Bug" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: /Core Bugfix Squad/ }),
  ).toBeChecked();
  await page.goto(`${projectUrl}/settings`);
  await page.getByLabel("Mô tả", { exact: true }).fill("Updated settings");
  await page.getByRole("button", { name: "Lưu cài đặt" }).click();
  await expect(page.getByText("Đã lưu project", { exact: true })).toBeVisible();
  for (let i = 2; i <= 6; i++) {
    const response = await page.request.post("/api/backend/projects", {
      data: {
        name: `Project ${i}`,
        workspace_path: path.resolve(".e2e-data/workspace"),
        default_branch: "develop",
      },
    });
    expect(response.ok()).toBe(true);
  }
  await page.reload();
  await expect(page.getByTestId("sidebar-project")).toHaveCount(5);
  await expect(
    page.getByRole("button", { name: "Xem tất cả (6)" }),
  ).toBeVisible();
  const ordered = await Promise.all(
    (await page.getByTestId("sidebar-project").all()).map((item) =>
      item.getByRole("link").first().innerText(),
    ),
  );
  expect(ordered[4]).toBe("Phase 4 Project");
  await page.getByRole("link", { name: "Project 6", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Project 6", exact: true }),
  ).toBeVisible();
  await expect(page.getByTestId("sidebar-project")).toHaveCount(5);
  expect(
    await Promise.all(
      (await page.getByTestId("sidebar-project").all()).map((item) =>
        item.getByRole("link").first().innerText(),
      ),
    ),
  ).toEqual([...ordered.slice(0, 4), "Project 2"]);
  await page.screenshot({ path: ".e2e-data/management-desktop.png" });
  await page.getByRole("link", { name: /Agents & Teams/ }).click();
  await page.getByRole("heading", { name: "Agents", exact: true }).waitFor();
  await expect(
    page.getByRole("article").filter({
      has: page.getByRole("heading", {
        name: "Core Bugfix Squad",
        exact: true,
      }),
    }),
  ).toContainText("4 agent · dùng trong 1 project");
  await page.screenshot({ path: ".e2e-data/agents-verified.png" });
  await page.setViewportSize({ width: 900, height: 800 });
  await expect(
    page.getByRole("complementary", { name: "Sidebar" }),
  ).toBeHidden();
  await page.getByRole("button", { name: "Mở menu" }).click();
  await expect(
    page.getByRole("complementary", { name: "Sidebar" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Đóng sidebar" }).click();
  await expect(
    page.getByRole("complementary", { name: "Sidebar" }),
  ).toBeHidden();
  expect(errors).toEqual([]);
});

test("real backend: logo upload, edit/delete management entities, CSRF and logout", async ({
  page,
}) => {
  test.setTimeout(120000);
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Mật khẩu").fill("test-password-123");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  const denied = await page.request.post("/api/backend/projects", {
    headers: { Origin: "https://untrusted.example" },
    data: {},
  });
  expect(denied.status()).toBe(403);
  const oldTeams = await page.request.get("/teams", { maxRedirects: 0 });
  expect(oldTeams.status()).toBe(308);
  expect(oldTeams.headers().location).toMatch(/\/agents$/);
  const created = await page.request.post("/api/backend/agents", {
    data: {
      handle: "@crud_agent",
      display_name: "CRUD Agent",
      runtime: "codex",
    },
  });
  expect(created.ok()).toBe(true);
  const agent = await created.json();
  const teamResponse = await page.request.post("/api/backend/teams", {
    data: { name: "CRUD Team", agent_ids: [agent.id] },
  });
  expect(teamResponse.ok()).toBe(true);
  const team = await teamResponse.json();
  // Fixture writes bypass React Query mutations; reload to discard the cached sidebar lists.
  await page.goto("/agents");
  await page
    .getByRole("button", { name: "Sửa team CRUD Team", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Tên AI Team", { exact: true })
    .fill("CRUD Team Updated");
  await dialog.getByLabel("Tải logo").setInputFiles({
    name: "logo.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGN0m3aCgYGBiQEMABNYAag5urDyAAAAAElFTkSuQmCC",
      "base64",
    ),
  });
  await expect(dialog.getByRole("img", { name: "Logo" })).toBeVisible();
  await dialog.getByRole("button", { name: "Lưu AI Team" }).click();
  await expect(dialog).toHaveCount(0);
  const updated = await (
    await page.request.get(`/api/backend/teams/${team.id}`)
  ).json();
  expect(updated.logo_url).toMatch(/^\/api\/assets\/logos\//);
  const image = await page.request.get(
    updated.logo_url.replace("/api/", "/api/backend/"),
  );
  expect(image.ok()).toBe(true);
  expect(image.headers()["content-type"]).toContain("image/png");
  await page
    .getByRole("button", { name: "Xoá team CRUD Team Updated", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xác nhận", exact: true })
    .click();
  await expect(
    page.getByRole("button", {
      name: "Xoá team CRUD Team Updated",
      exact: true,
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Xoá @crud_agent", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xác nhận", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Sửa @crud_agent", exact: true }),
  ).toHaveCount(0);
  const project = await (
    await page.request.post("/api/backend/projects", {
      data: {
        name: "Delete Project",
        workspace_path: path.resolve(".e2e-data/workspace"),
        default_branch: "develop",
      },
    })
  ).json();
  const person = (
    await (await page.request.get("/api/backend/users")).json()
  )[0];
  await page.request.post(`/api/backend/projects/${project.id}/members`, {
    data: {
      member_type: "USER",
      member_id: person.id,
      project_role: "REPORTER",
    },
  });
  await page.goto(`/projects/${project.id}/members`);
  await page.getByRole("button", { name: "Gỡ", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Gỡ", exact: true }),
  ).toHaveCount(0);
  await page.goto(`/projects/${project.id}/settings`);
  await page.getByRole("button", { name: "Xoá project", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xác nhận", exact: true })
    .click();
  await expect(page).toHaveURL(/\/projects$/);
  expect(
    (await page.request.get(`/api/backend/projects/${project.id}`)).status(),
  ).toBe(404);
  await page.getByRole("button", { name: "Đăng xuất", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(
    (await page.context().cookies()).some((c) => c.name === "aiteams_session"),
  ).toBe(false);
});
