import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
test.use({ actionTimeout: 20000 });
const image = {
  name: "screen.png",
  mimeType: "image/png",
  buffer: readFileSync(path.resolve("e2e/fixtures/chat.png")),
};
async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("owner@example.com");
  await page.getByLabel("Mật khẩu").fill("test-password-123");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/, { timeout: 45000 });
}
async function makeProject(page: Page, name: string) {
  const runtime = JSON.parse(
    readFileSync(path.resolve(".e2e-data/runtime.json"), "utf8"),
  );
  const response = await page.request.post("/api/backend/projects", {
    data: {
      name,
      workspace_path: runtime.workspace,
      default_branch: "develop",
    },
  });
  expect(response.ok()).toBe(true);
  const project = await response.json();
  const seeded = await (
    await page.request.post(`/api/backend/projects/${project.id}/seed-default`)
  ).json();
  return { project, workflow: seeded.workflow, runtime };
}
test("chat: auto-start, clarify, attachments, preferences, reconnect, reject, two-tab approval and real Git release", async ({
  page,
  context,
}) => {
  test.setTimeout(240000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page);
  const { project, workflow, runtime } = await makeProject(page, "Ticket Chat");
  await page.goto(`/projects/${project.id}/workflows/${workflow.id}`);
  await page.getByRole("button", { name: "+ Tạo ticket", exact: true }).click();
  await page
    .getByLabel("Tiêu đề", { exact: true })
    .fill("Bấm nút xuất Excel không tải được file");
  await page
    .getByLabel("Mô tả lỗi/yêu cầu")
    .fill("Trên màn hình đối soát, bấm Xuất Excel không có phản hồi.");
  await page
    .getByRole("button", { name: "Tạo & mở chat", exact: true })
    .click();
  await expect(page).toHaveURL(/\/tickets\/[a-f0-9-]+$/);
  const url = page.url();
  const tid = url.split("/").at(-1)!;
  await expect(page.getByTestId("ticket-channel")).toBeVisible();
  await expect(page.locator("#clarify-prompt")).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "Chọn agent mặc định" }).click();
  await page
    .getByRole("dialog", { name: "Gửi tới agent", exact: true })
    .getByRole("button", { name: /@developer/ })
    .click();
  await expect(
    page.getByRole("button", { name: "Chọn agent mặc định" }),
  ).toContainText("@developer");
  await page.getByLabel("Chọn tệp đính kèm").setInputFiles([
    image,
    {
      name: "remove.log",
      mimeType: "text/plain",
      buffer: Buffer.from("log"),
    },
  ]);
  await expect(page.getByLabel("Tệp chờ gửi")).toContainText("Đã tải");
  await page.getByRole("button", { name: "Gỡ remove.log" }).click();
  await expect(page.getByLabel("Tệp chờ gửi")).not.toContainText("remove.log");
  const data = await page.evaluateHandle(() => {
    const dt = new DataTransfer();
    dt.items.add(
      new File(["Browser: Chrome"], "browser.log", { type: "text/plain" }),
    );
    return dt;
  });
  await page
    .getByTestId("chat-composer")
    .dispatchEvent("drop", { dataTransfer: data });
  const pasted = await page.evaluateHandle((base64) => {
    const dt = new DataTransfer();
    dt.items.add(
      new File(
        [Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))],
        "pasted.png",
        { type: "image/png" },
      ),
    );
    return dt;
  }, image.buffer.toString("base64"));
  await page
    .getByRole("textbox", { name: "Tin nhắn", exact: true })
    .evaluate(
      (element, data) =>
        element.dispatchEvent(
          new ClipboardEvent("paste", {
            clipboardData: data as DataTransfer,
            bubbles: true,
            cancelable: true,
          }),
        ),
      pasted,
    );
  await expect(
    page.getByRole("button", { name: "Gỡ pasted.png" }),
  ).toBeVisible();
  await page.getByLabel("Chọn tệp đính kèm").setInputFiles(
    [1, 2, 3].map((n) => ({
      name: `extra${n}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from("extra"),
    })),
  );
  await expect(
    page.getByText("Tối đa 5 file mỗi tin nhắn", { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Gỡ extra3.txt" })).toHaveCount(
    0,
  );
  await expect(
    page.getByLabel("Tệp chờ gửi").getByText(/Đang tải/),
  ).toHaveCount(0);
  // Draft files survive navigating to a different channel and back.
  const stopped = (
    await (
      await page.request.post(`/api/backend/workflows/${workflow.id}/tickets`, {
        data: { title: "Draft persistence", auto_start: false },
      })
    ).json()
  ).ticket;
  const expand = page.getByRole("button", {
    name: "Mở workflow Fix Bug",
    exact: true,
  });
  if (await expand.count()) await expand.click();
  await page.locator(`a[href$="/tickets/${stopped.id}"]`).click();
  await expect(
    page.getByRole("button", { name: /Bắt đầu xử lý/ }),
  ).toBeVisible();
  await page.getByRole("link", { name: /bug-bam-nut-xuat-excel/ }).click();
  await expect(page.getByLabel("Tệp chờ gửi")).toContainText("screen.png");
  await page
    .getByRole("textbox", { name: "Tin nhắn", exact: true })
    .fill("Chrome, mở đối soát rồi bấm Xuất Excel; hãy làm nhanh.");
  await page.getByRole("button", { name: "Gửi tin nhắn", exact: true }).click();
  await expect(
    page
      .getByRole("article", { name: "Tin nhắn Owner" })
      .filter({ hasText: "hãy làm nhanh" }),
  ).toContainText("@developer");
  await expect(
    page.getByRole("button", { name: "Phóng to screen.png", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("article", { name: "Lượt @developer", exact: true }).first(),
  ).toContainText("Guard: Đã chặn");
  await expect(page.getByText(/Xem thay đổi mã nguồn/).first()).toBeVisible();
  await expect(page.locator("#confirm-box")).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("article", { name: "Lượt @developer", exact: true })
    .first()
    .getByRole("button", { name: "Mở log lượt agent" })
    .click();
  await expect(
    page.getByRole("article", { name: "Lượt @developer", exact: true }).first(),
  ).toContainText("DENY");
  await page
    .getByRole("button", { name: "Xem toàn bộ log của ticket →" })
    .first()
    .click();
  await expect(
    page.getByRole("dialog", { name: "Toàn bộ log của ticket" }),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Lọc log theo agent" })
    .selectOption("@developer");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Đóng", exact: true })
    .click();
  // Disconnect the transport, then resume from the last contiguous sequence.
  await page.route("**/api/events?channel=tickets/**", (route) =>
    route.abort(),
  );
  await context.setOffline(true);
  await context.setOffline(false);
  await page.unroute("**/api/events?channel=tickets/**");
  await page.reload();
  await expect(page.locator("#confirm-box")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Chọn agent mặc định" }),
  ).toContainText("@developer");
  await page
    .locator("#confirm-box")
    .getByRole("button", { name: /Chưa đạt/ })
    .click();
  await page
    .getByLabel("Điểm chưa đạt")
    .fill("Cần kiểm tra file Excel có dữ liệu đầy đủ.");
  await page
    .getByRole("button", { name: "Gửi yêu cầu sửa lại", exact: true })
    .click();
  await expect(page.getByText(/Luồng đã quay lại @developer/)).toBeVisible();
  await expect(page.locator("#confirm-box")).toBeVisible({ timeout: 30000 });
  const second = await context.newPage();
  await second.goto(url);
  await expect(second.locator("#confirm-box")).toBeVisible();
  await page.screenshot({
    path: ".e2e-data/ticket-chat-waiting.png",
    fullPage: true,
  });
  await page
    .locator("#confirm-box")
    .getByRole("button", { name: /Xác nhận/ })
    .click();
  await expect(second.locator("#confirm-box")).toHaveCount(0);
  await expect(
    page.getByText(/Hoàn tất: Commit .*đã được đẩy lên Git/),
  ).toBeVisible({ timeout: 30000 });
  await expect(
    second.getByText(/Hoàn tất: Commit .*đã được đẩy lên Git/),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Gửi tin nhắn" }),
  ).toBeDisabled();
  const final = await (
    await page.request.get(`/api/backend/tickets/${tid}`)
  ).json();
  expect(final.status).toBe("COMPLETED");
  expect(final.result.commit_hash).toBeTruthy();
  const prompts = readFileSync(
    path.join(runtime.workspace, ".aiteams/prompt-checks.jsonl"),
    "utf8",
  );
  expect(prompts).toContain("screen.png");
  expect(prompts).toContain("browser.log");
  const rows = await (
    await page.request.get(`/api/backend/tickets/${tid}/messages?limit=1000`)
  ).json();
  expect(new Set(rows.map((r: { seq: number }) => r.seq)).size).toBe(
    rows.length,
  );
  expect(
    (
      await (
        await page.request.get("/api/backend/notifications?status=open")
      ).json()
    ).items.filter((n: { ticket_id: string }) => n.ticket_id === tid),
  ).toHaveLength(0);
  // Default mention also applies in a different project.
  const other = await makeProject(page, "Other Chat Project");
  const otherTicket = (
    await (
      await page.request.post(
        `/api/backend/workflows/${other.workflow.id}/tickets`,
        { data: { title: "Other project chat" } },
      )
    ).json()
  ).ticket;
  await page.goto(
    `/projects/${other.project.id}/workflows/${other.workflow.id}/tickets/${otherTicket.id}`,
  );
  await expect(
    page.getByRole("button", { name: "Chọn agent mặc định" }),
  ).toContainText("@developer");
  await page.request.post(`/api/backend/tickets/${otherTicket.id}/cancel`);
  await page.goto(url);
  await expect(page.getByRole("article", { name: "Lượt @leader", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Xem workflow của ticket" }).click();
  await expect(
    page.getByRole("dialog", { name: /Tiến độ workflow v1/ }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Đóng", exact: true })
    .click();
  await page.screenshot({
    path: ".e2e-data/ticket-chat-completed.png",
    fullPage: true,
  });
  await second.close();
  expect(errors).toEqual([]);
});
