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
    page.getByRole("heading", { name: "Your activity" }),
  ).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(1);
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
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.context().clearCookies();
  await page.getByRole("textbox", { name: "Nhập tin nhắn" }).fill("expired");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(
    page.getByRole("heading", { name: "Chào mừng trở lại." }),
  ).toBeVisible();
  await expect(page.locator(".message-content")).toHaveCount(0);
});
