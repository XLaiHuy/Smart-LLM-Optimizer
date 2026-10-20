import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, user = "e2e-a") {
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập", { exact: true }).fill(user);
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Mật khẩu", { exact: true })).toBeFocused();
  await page
    .getByLabel("Mật khẩu", { exact: true })
    .fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Một không gian. Nhiều khả năng." }),
  ).toBeVisible();
}

test("owned chat, no-op flags, trace, locale preserves draft, resume, overview and logout", async ({
  page,
}, testInfo) => {
  await login(page);
  await page.screenshot({
    path: testInfo.outputPath("workspace.png"),
    fullPage: true,
  });
  const composer = page.getByRole("textbox", { name: "Nhập tin nhắn" });
  await composer.fill("Bản nháp tiếng Việt");
  await page.getByRole("button", { name: "EN", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "Your message" })).toHaveValue(
    "Bản nháp tiếng Việt",
  );
  await page.getByRole("button", { name: "Optimized", exact: true }).click();
  await page.getByRole("button", { name: "Request configuration" }).click();
  await page.getByRole("switch", { name: "Conversation memory" }).click();
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByRole("button", { name: "View trace", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "View trace", exact: true }).click();
  const drawer = page.getByRole("dialog");
  await expect(
    drawer.getByText("Not implemented", { exact: true }),
  ).toHaveCount(3);
  await expect(drawer.getByText("Disabled", { exact: true })).toHaveCount(1);
  await expect(
    drawer.getByText("No live measurements yet", { exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await page.reload();
  await page
    .getByRole("button", { name: "Bản nháp tiếng Việt", exact: true })
    .click();
  await expect(page.locator(".message.user")).toContainText(
    "Bản nháp tiếng Việt",
  );
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Activity & costs" }),
  ).toBeVisible();
  await expect(page.locator(".recent-activity tbody tr")).toHaveCount(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await expect(
    page.getByText("Bản nháp tiếng Việt", { exact: true }),
  ).toHaveCount(0);
});

test("second user isolation and invalid credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Tên đăng nhập", { exact: true }).fill("e2e-b");
  await page.getByLabel("Mật khẩu", { exact: true }).fill("wrong");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(page.locator(".error-notice[role=alert]")).toContainText(
    "Tên đăng nhập/mật khẩu",
  );
  await page
    .getByLabel("Mật khẩu", { exact: true })
    .fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(
    page.getByText("Chưa có hội thoại", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Bản nháp tiếng Việt", { exact: true }),
  ).toHaveCount(0);
});

test("mobile, network retry keeps request ID, auth expiry clears private UI", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "e2e-b");
  await page.getByRole("button", { name: "Mở lịch sử" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Đóng", exact: true }).click();
  let fail = true;
  const ids: string[] = [];
  await page.route("**/api/v1/chat", async (route) => {
    ids.push(route.request().postDataJSON().client_request_id);
    if (fail) {
      fail = false;
      await route.abort("failed");
    } else await route.continue();
  });
  await page
    .getByRole("textbox", { name: "Nhập tin nhắn" })
    .fill("Mobile retry");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(page.locator(".error-notice[role=alert]")).toContainText(
    "Mất kết nối",
  );
  await page.getByRole("button", { name: "Thử lại", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Xem trace", exact: true }),
  ).toBeVisible();
  expect(new Set(ids).size).toBe(1);
  await expect.poll(async()=>page.evaluate(()=>({root:document.documentElement.scrollWidth, viewport:window.innerWidth}))).toEqual({root:390, viewport:390});
  await page.context().clearCookies();
  try {
    await page
      .getByRole("textbox", { name: "Nhập tin nhắn" })
      .fill("expired", { timeout: 1500 });
    await page
      .getByRole("button", { name: "Gửi tin nhắn" })
      .click({ timeout: 1500 });
  } catch {
    // Background query 401 already triggered auth expiry
  }
  await expect(
    page.getByRole("heading", { name: "Chào mừng trở lại." }),
  ).toBeVisible();
  await expect(page.locator(".message-content")).toHaveCount(0);
});

test("documents, citations, full-text jobs and analytics exports", async ({
  page,
}, testInfo) => {
  await login(page);
  await page.locator(".document-panel>summary").click();
  await page.getByLabel("Tải tài liệu", { exact: true }).setInputFiles({
    name: "hoc-phi.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(
      "Học phí là 12 triệu đồng. Hạn đóng là 25/10/2026.",
      "utf8",
    ),
  });
  await expect(
    page.getByRole("checkbox", { name: "Dùng làm nguồn hoc-phi.txt" }),
  ).toBeVisible();
  if (!(await page.locator(".document-body").isVisible()))
    await page.locator(".document-panel>summary").click();
  await page
    .getByRole("checkbox", { name: "Dùng làm nguồn hoc-phi.txt" })
    .check();
  await page.getByRole("button", { name: "Lập chỉ mục", exact: true }).click();
  await expect(page.getByText("Sẵn sàng", { exact: false })).toBeVisible();
  await page
    .getByRole("textbox", { name: "Nhập tin nhắn" })
    .fill("Học phí bao nhiêu?");
  await page.getByRole("button", { name: "Gửi tin nhắn", exact: true }).click();
  await expect(page.locator(".message.assistant")).toHaveCount(1);
  await page.getByRole("button", { name: "Xem trace", exact: true }).click();
  const drawer = page.getByRole("dialog");
  await expect(
    drawer.getByRole("heading", { name: "Nguồn được dùng" }),
  ).toBeVisible();
  await drawer.locator(".source-card>summary").first().click();
  await expect(drawer.locator(".source-card pre").first()).toContainText(
    "12 triệu",
  );
  await page.keyboard.press("Escape");
  if (!(await page.locator(".document-body").isVisible()))
    await page.locator(".document-panel>summary").click();
  await page
    .getByRole("button", { name: "Tóm tắt toàn văn", exact: true })
    .click();
  await expect(page.locator(".message.assistant")).toHaveCount(2);
  await page.screenshot({
    path: testInfo.outputPath("documents.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.locator(".message.assistant")).toHaveCount(2);
  await page.getByRole("link", { name: "Tổng quan", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Hoạt động & chi phí" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Xuất CSV" })).toHaveAttribute(
    "href",
    /format=csv/,
  );
  await expect(page.locator(".chart-grid")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("analytics.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(async()=>page.evaluate(()=>({root:document.documentElement.scrollWidth, viewport:window.innerWidth}))).toEqual({root:390, viewport:390});
});

test("admin aggregated usage and audited quota update", async ({ page }) => {
  await login(page, "e2e-admin");
  await page.getByRole("link", { name: "Tổng quan", exact: true }).click();
  await page
    .getByRole("combobox", { name: "Toàn project", exact: true })
    .selectOption("project");
  await expect(
    page.getByRole("heading", { name: "Tài khoản & quota" }),
  ).toBeVisible();
  const row = page
    .locator(".quota-row")
    .filter({ has: page.getByText("e2e-b", { exact: true }) });
  await row.getByLabel("Hạn mức USD").fill("4.50");
  await row.getByLabel("Lý do thay đổi").fill("E2E quota adjustment");
  await row.getByRole("button", { name: "Lưu quota", exact: true }).click();
  await expect(row.getByRole("status")).toContainText("Đã cập nhật quota.");
});
