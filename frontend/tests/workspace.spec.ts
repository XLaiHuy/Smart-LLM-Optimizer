import { test, expect, type Page } from "@playwright/test";

async function login(page: Page, user = "e2e-a") {
  await page.goto("/");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
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

test("settings, three models, architecture, legacy redirects and mobile", async ({
  page,
}, testInfo) => {
  await login(page, "e2e-admin");
  await expect(
    page.getByRole("link", { name: "Thử nghiệm hiệu năng", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("link", { name: "Cài đặt", exact: true }).click();
  await expect(page.locator(".settings-page h1")).toBeVisible();
  await expect(
    page
      .locator(".settings-card")
      .filter({ has: page.locator(".model-planet-cards") })
      .first()
      .locator(".planet-card"),
  ).toHaveCount(3);
  await page.getByRole("tab", { name: "Kiến trúc", exact: true }).click();
  await expect(page.locator(".architecture-stages > li")).toHaveCount(7);
  const demo = page.locator('.trace-scene[data-simulation="true"]');
  await demo.scrollIntoViewIfNeeded();
  await expect(demo).toHaveAttribute("data-animation-state", "running");
  const firstStage = await demo.getAttribute("data-flow-stage");
  await expect
    .poll(() => demo.getAttribute("data-flow-stage"))
    .not.toBe(firstStage);
  await page
    .getByRole("button", { name: "Tạm dừng mô phỏng", exact: true })
    .click();
  await expect(demo).toHaveAttribute("data-animation-state", "paused");
  await page
    .getByRole("button", { name: "Chạy mô phỏng", exact: true })
    .click();
  await expect(demo).toHaveAttribute("data-animation-state", "running");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(demo).toHaveAttribute("data-animation-state", "paused");
  await page.emulateMedia({ reducedMotion: "no-preference" });

  await page.screenshot({
    path: testInfo.outputPath("settings-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("settings-mobile.png"),
    fullPage: true,
  });
  for (const path of ["/research", "/pipeline", "/research-guide"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("textbox", { name: "Nhập tin nhắn" }),
    ).toBeVisible();
  }
});

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
  await page.getByRole("button", { name: "Automatic", exact: true }).click();
  await page.getByRole("button", { name: "Request configuration" }).click();
  await page.getByRole("switch", { name: "Conversation memory" }).click();
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    page.getByRole("button", { name: "Optimization & cost log", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Optimization & cost log", exact: true })
    .click();
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
  await expect(page.getByRole("heading", { name: "Your usage" })).toBeVisible();
  const conversationUsage = page
    .locator("td.metric-key")
    .filter({ hasText: /^Bản nháp tiếng Việt$/ });
  await expect(conversationUsage).toHaveCount(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await expect(
    page.getByText("Bản nháp tiếng Việt", { exact: true }),
  ).toHaveCount(0);
});

test("second user isolation and invalid credentials", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
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
    page.getByRole("button", { name: "Chi tiết Xử lý AI", exact: true }),
  ).toBeVisible();
  expect(new Set(ids).size).toBe(1);
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        root: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      })),
    )
    .toEqual({ root: 390, viewport: 390 });
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
  await page
    .getByRole("button", { name: "Chi tiết Xử lý AI", exact: true })
    .click();
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
  await page
    .getByRole("link", { name: "Thống kê sử dụng", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Mức sử dụng của bạn" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "CSV", exact: true }),
  ).toHaveAttribute("href", /format=csv/);
  await expect(page.locator(".chart-grid")).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("analytics.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () =>
      page.evaluate(() => ({
        root: document.documentElement.scrollWidth,
        viewport: window.innerWidth,
      })),
    )
    .toEqual({ root: 390, viewport: 390 });
});

test("admin aggregated usage and audited quota update", async ({ page }) => {
  await login(page, "e2e-admin");
  await page
    .getByRole("link", { name: "Thống kê sử dụng", exact: true })
    .click();
  await page.getByRole("button", { name: "Toàn dự án", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Thống kê theo tài khoản" }),
  ).toBeVisible();
  const row = page
    .locator(".quota-row")
    .filter({ has: page.getByText("e2e-b", { exact: true }) });
  await row.getByLabel("Hạn mức USD").fill("4.50");
  await row.getByLabel("Lý do điều chỉnh").fill("E2E quota adjustment");
  await row.getByRole("button", { name: "Lưu quota", exact: true }).click();
  await expect(row.getByRole("status")).toContainText("Đã cập nhật quota.");
});
