import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
test.use({ actionTimeout: 15000 });
async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Mật khẩu").fill("test-password-123");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/, { timeout: 45000 });
}
async function wizard(
  page: Page,
  name: string,
  prefix: string,
  source?: string,
) {
  await page.getByLabel("Tên workflow", { exact: true }).fill(name);
  await page.getByLabel("Prefix ticket", { exact: true }).fill(prefix);
  await page.getByRole("button", { name: "Tiếp tục", exact: true }).click();
  if (source) {
    await page
      .getByRole("radio", { name: "Nhân bản từ workflow có sẵn" })
      .check();
    await page
      .getByRole("combobox", { name: "Workflow nguồn" })
      .selectOption(source);
  }
  await page.getByRole("button", { name: "Tiếp tục", exact: true }).click();
  await page
    .getByRole("button", { name: "Tạo & mở canvas", exact: true })
    .click();
  await expect(page.getByTestId("workflow-editor")).toBeVisible();
}
async function publish(page: Page) {
  await page.getByRole("button", { name: "Xuất bản", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xác nhận", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
}
async function connect(
  page: Page,
  source: string,
  handle: string,
  target: string,
) {
  await page
    .locator(
      `.react-flow__handle[data-nodeid="${source}"][data-handleid="${handle}"]`,
    )
    .click();
  await page
    .locator(`.react-flow__handle.target[data-nodeid="${target}"]`)
    .click();
  await expect(
    page.locator(
      `.react-flow__edge[aria-label="Edge from ${source} to ${target}"]`,
    ),
  ).toHaveCount(1);
}
test("workflow builder: empty project, wizard, publish, clone, drag security, wire, save/reload and archive", async ({
  page,
}) => {
  test.setTimeout(240000);
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await login(page);
  const projectResponse = await page.request.post("/api/backend/projects", {
    data: {
      name: "HNBG Builder",
      workspace_path: path.resolve(".e2e-data/workspace"),
      default_branch: "develop",
    },
  });
  expect(projectResponse.ok()).toBe(true);
  const project = await projectResponse.json();
  await page.goto(`/projects/${project.id}`);
  await expect(
    page.getByText(
      "Chưa có agent nào — hãy thêm AI Team trước khi tạo workflow.",
    ),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Thành viên & AI Team", exact: true })
    .click();
  await page.getByRole("checkbox", { name: /Core Bugfix Squad/ }).check();
  await expect(
    page.getByRole("checkbox", { name: /Core Bugfix Squad/ }),
  ).toBeEnabled();
  await page.getByRole("link", { name: "Về project", exact: true }).click();
  await page.getByRole("link", { name: "Tạo workflow", exact: true }).click();
  await wizard(page, "Fix Bug Builder", "BLD");
  const firstUrl = page.url(),
    firstId = firstUrl.split("/").at(-2)!;
  await expect(
    page.getByRole("button", { name: "Tạo ticket đầu tiên" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Pipeline", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Pipeline workflow" }),
  ).toBeVisible();
  await expect(
    page.getByText("↺ Fail: quay lại bước 2", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Canvas", exact: true }).click();
  await publish(page);
  await expect(
    page.getByRole("button", { name: "Tạo ticket đầu tiên" }),
  ).toBeVisible();
  // Add a custom agent after the editor was created; it must appear once it is a project member.
  const securityResponse = await page.request.post("/api/backend/agents", {
    data: {
      handle: "@builder_security",
      display_name: "Security Checker",
      role_key: "SECURITY",
      runtime: "codex",
    },
  });
  expect(securityResponse.ok()).toBe(true);
  const security = await securityResponse.json();
  await page.goto(`/projects/${project.id}/members`);
  await page.getByRole("checkbox", { name: /@builder_security/ }).check();
  await expect(
    page.getByRole("checkbox", { name: /@builder_security/ }),
  ).toBeEnabled();
  await page.goto(`/projects/${project.id}/workflows/new`);
  await wizard(page, "Fix Bug Security", "SEC", firstId);
  await expect(
    page.getByRole("button", { name: "Thêm @builder_security", exact: true }),
  ).toBeVisible();
  const secondUrl = page.url(),
    secondId = secondUrl.split("/").at(-2)!;
  await page
    .getByRole("button", { name: "Thêm @builder_security", exact: true })
    .dragTo(page.getByTestId("workflow-canvas"), {
      targetPosition: { x: 280, y: 80 },
    });
  const inspector = page.getByRole("complementary", { name: "Cấu hình node" });
  await expect(
    inspector.getByRole("combobox", { name: "Agent", exact: true }),
  ).toHaveValue(security.id);
  await inspector
    .getByRole("combobox", { name: "Routing" })
    .selectOption("review");
  await inspector
    .getByLabel("Hướng dẫn bổ sung cho bước này")
    .fill("Review security before tests");
  const node = page.locator(".react-flow__node.selected");
  const securityNodeId = await node.getAttribute("data-id");
  expect(securityNodeId).toBeTruthy();
  // Remove the developer -> tester edge by selecting its SVG curve, then wire via real handles.
  const edgePath = page.locator(
    '.react-flow__edge[data-id="e4"] path.react-flow__edge-path',
  );
  const point = await edgePath.evaluate((path) => {
    const p = path as SVGPathElement;
    const at = p.getPointAtLength(p.getTotalLength() * 0.5);
    const screen = new DOMPoint(at.x, at.y).matrixTransform(p.getScreenCTM()!);
    return { x: screen.x, y: screen.y };
  });
  await page.mouse.click(point.x, point.y);
  await page.keyboard.press("Delete");
  await expect(page.locator('.react-flow__edge[data-id="e4"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Sắp xếp", exact: true }).click();
  await connect(page, "n_dev", "default", securityNodeId!);
  await connect(page, securityNodeId!, "pass", "n_test");
  await connect(page, securityNodeId!, "fail", "n_dev");
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(
    page.getByText("Đã lưu workflow hợp lệ", { exact: true }),
  ).toBeVisible();
  const before = await (
    await page.request.get(`/api/backend/workflows/${secondId}`)
  ).json();
  expect(before.is_valid).toBe(true);
  expect(before.graph.nodes).toHaveLength(9);
  expect(before.current_version).toBeGreaterThan(1);
  await page.reload();
  await expect(page.getByTestId(`flow-node-${securityNodeId}`)).toBeVisible();
  const after = await (
    await page.request.get(`/api/backend/workflows/${secondId}`)
  ).json();
  expect(after.graph).toEqual(before.graph);
  await publish(page);
  await expect(
    page
      .getByRole("complementary", { name: "Sidebar", exact: true })
      .getByRole("link", { name: /Fix Bug Builder.*BLD/ }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("complementary", { name: "Sidebar", exact: true })
      .getByRole("link", { name: /Fix Bug Security.*SEC/ }),
  ).toBeVisible();
  // Dirty navigation is guarded and keyboard undo/redo removes/restores a duplicate.
  await page.getByTestId(`flow-node-${securityNodeId}`).click();
  await page.keyboard.press("Control+d");
  await expect(page.locator(".react-flow__node")).toHaveCount(10);
  await page.keyboard.press("Control+z");
  await expect(page.locator(".react-flow__node")).toHaveCount(9);
  await page.keyboard.press("Control+y");
  await expect(page.locator(".react-flow__node")).toHaveCount(10);
  page.once("dialog", (dialog) => dialog.dismiss());
  await page
    .getByRole("link", { name: "HNBG Builder", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(secondUrl);
  await page.keyboard.press("Control+z");
  await page.getByRole("button", { name: "Sắp xếp", exact: true }).click();
  await page.keyboard.press("Control+s");
  await expect(
    page.getByText("Đã lưu workflow hợp lệ", { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: ".e2e-data/workflow-builder.png" });
  await page.goto(`/projects/${project.id}/workflows/new`);
  await page
    .getByLabel("Tên workflow", { exact: true })
    .fill("Duplicate prefix");
  await page.getByLabel("Prefix ticket", { exact: true }).fill("BLD");
  await expect(
    page.getByText("Prefix BLD đã tồn tại trong project."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Tiếp tục", exact: true }),
  ).toBeDisabled();
  await page.goto(`/projects/${project.id}/workflows`);
  const card = page.getByRole("article", {
    name: "Workflow Fix Bug Security",
    exact: true,
  });
  await card.getByLabel("Thao tác Fix Bug Security", { exact: true }).click();
  await card.getByRole("button", { name: "Lưu trữ", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Xác nhận", exact: true })
    .click();
  await expect(
    card.getByRole("button", { name: "Tạo ticket", exact: true }),
  ).toBeDisabled();
  expect(
    (await (await page.request.get(`/api/backend/workflows/${firstId}`)).json())
      .status,
  ).toBe("PUBLISHED");
  expect(pageErrors).toEqual([]);
});

test("30-node canvas: drag, connect, delete, undo/redo and save invalid draft", async ({
  page,
}) => {
  test.setTimeout(120000);
  await login(page);
  const project = await (
    await page.request.post("/api/backend/projects", {
      data: {
        name: "Large Builder",
        workspace_path: path.resolve(".e2e-data/workspace"),
        default_branch: "develop",
      },
    })
  ).json();
  const workflow = await (
    await page.request.post(`/api/backend/projects/${project.id}/workflows`, {
      data: { name: "Thirty nodes", ticket_prefix: "LARGE", template: "blank" },
    })
  ).json();
  const nodes = Array.from({ length: 30 }, (_, i) => ({
    id: `large_${i}`,
    type: i === 0 ? "start" : i === 29 ? "end" : "human_input",
    position: { x: (i % 6) * 330, y: Math.floor(i / 6) * 200 },
    data: { label: `Step ${i}` },
  }));
  const edges = nodes.slice(0, -1).map((n, i) => ({
    id: `large_e${i}`,
    source: n.id,
    target: nodes[i + 1].id,
  }));
  expect(
    (
      await page.request.put(`/api/backend/workflows/${workflow.id}/graph`, {
        data: { nodes, edges },
      })
    ).ok(),
  ).toBe(true);
  await page.goto(`/projects/${project.id}/workflows/${workflow.id}/edit`);
  await expect(page.locator(".react-flow__node")).toHaveCount(30);
  const first = page.getByTestId("flow-node-large_0");
  await first.click();
  const original = await page
    .locator('.react-flow__node[data-id="large_0"]')
    .getAttribute("style");
  const box = await first.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width / 2 + 35,
    box!.y + box!.height / 2 + 20,
    { steps: 8 },
  );
  await page.mouse.up();
  await expect(
    page.locator('.react-flow__node[data-id="large_0"]'),
  ).not.toHaveAttribute("style", original!);
  await page.keyboard.press("Control+z");
  await expect(
    page.locator('.react-flow__node[data-id="large_0"]'),
  ).toHaveAttribute("style", original!);
  await page.getByTestId("flow-node-large_10").click();
  await page.keyboard.press("Delete");
  await expect(page.locator(".react-flow__node")).toHaveCount(29);
  await page.keyboard.press("Control+z");
  await expect(page.locator(".react-flow__node")).toHaveCount(30);
  await page.keyboard.press("Control+y");
  await expect(page.locator(".react-flow__node")).toHaveCount(29);
  await connect(page, "large_9", "default", "large_11");
  await page.getByRole("button", { name: "Lưu", exact: true }).click();
  await expect(
    page.getByText("Đã lưu workflow hợp lệ", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Thêm Hỏi người dùng", exact: true })
    .click();
  await expect(page.locator(".react-flow__node")).toHaveCount(30);
  await page.keyboard.press("Control+s");
  await expect(
    page.getByText("Đã lưu nháp. Sửa lỗi trước khi xuất bản.", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Xuất bản", exact: true }),
  ).toBeDisabled();
  await page.screenshot({ path: ".e2e-data/workflow-30-nodes.png" });
  await page.reload();
  await expect(page.locator(".react-flow__node")).toHaveCount(30);
});
