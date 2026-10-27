import { expect, test, type Page } from "@playwright/test";

async function login(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Tên đăng nhập", { exact: true }).fill("e2e-a");
  await dialog
    .getByLabel("Mật khẩu", { exact: true })
    .fill(process.env.E2E_PASSWORD!);
  await dialog.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "Nhập tin nhắn" }),
  ).toBeVisible();
}

test("chat, trace and Galaxy use actual model identity; fallback is not Attention execution", async ({
  page,
}, testInfo) => {
  await login(page);
  let saved: Record<string, unknown> | undefined;
  await page.route("**/api/v1/chat", async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    // Frontend transport fixture over a real mock execution: no live API call.
    data.execution_source = "live";
    data.response.content = "hai";
    data.effective_configuration.policy_id = "quality-guarded-v3";
    data.usage = {
      scope: "all_calls",
      input_tokens: 87,
      output_tokens: 91,
      cached_input_tokens: 0,
      reasoning_tokens: 81,
      usage_source: "provider",
    };
    data.cost = {
      scope: "all_calls",
      status: "estimated",
      serving_usd: "0.00006765",
      price_catalog_version: "smartllm-live-catalog-v3",
    };
    data.route = {
      ...data.route,
      config_id: "groq-llama-3.3-70b-versatile",
      model_id: "openai/gpt-oss-120b",
      reason: "ML_NOT_QUALIFIED_FALLBACK",
      reason_code: "ML_NOT_QUALIFIED_FALLBACK",
      fallback_used: true,
      ml_loaded: true,
      ml_executed: false,
      attention_loaded: false,
      attention_executed: false,
      attention_features: null,
    };
    data.calls = data.calls.map((call: Record<string, unknown>) => ({
      ...call,
      model_id: "openai/gpt-oss-120b",
      provider_host: "api.groq.com",
    }));
    saved = data;
    await route.fulfill({ response, json: data });
  });
  await page.route("**/api/v1/traces/*", async (route) => {
    if (saved && route.request().url().endsWith(String(saved.request_id)))
      await route.fulfill({ json: saved });
    else await route.continue();
  });
  await page.route("**/api/v1/requests/*/execution", async (route) => {
    if (saved)
      await route.fulfill({
        json: {
          request_id: saved.request_id,
          status: "succeeded",
          route: saved.route,
          calls: saved.calls,
          events: [],
          legacy: true,
        },
      });
    else await route.continue();
  });
  await page
    .getByRole("textbox", { name: "Nhập tin nhắn" })
    .fill("1 + 1 = mấy?");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  const badge = page.locator(".metrics-model-pill").last();
  await expect(badge).toContainText("GPT OSS 120B");
  await expect(badge).not.toContainText("Llama");
  await badge.click();
  await expect(page.locator(".trace-content")).toContainText(
    "ML_NOT_QUALIFIED_FALLBACK",
  );
  await expect(page.locator(".trace-experience .planet-card")).toHaveCount(3);
  await expect(page.locator(".planet-card.selected")).toHaveAttribute(
    "data-model-id",
    "openai/gpt-oss-120b",
  );
  await expect(page.locator(".attention-bars")).toHaveCount(0);
  await expect(page.locator(".execution-calls")).toContainText("GPT-OSS 120B");
  await page.screenshot({
    path: testInfo.outputPath("actual-model-trace.png"),
    fullPage: true,
  });
  await page
    .locator(".trace-experience")
    .screenshot({ path: testInfo.outputPath("actual-route-galaxy.png") });
});

test("lost preset response recovers by GET without another provider POST", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  const ids: string[] = [];
  let sessionId = "";
  let first = true;
  await page.route("**/api/v1/chat", async (route) => {
    const body = route.request().postDataJSON();
    ids.push(body.client_request_id);
    sessionId = body.session_id;
    const response = await route.fetch();
    if (first) {
      first = false;
      await route.abort("failed");
    } else await route.fulfill({ response });
  });
  await page
    .locator(".quick-showcase-btn")
    .first()
    .evaluate((button: HTMLButtonElement) => {
      button.click();
      button.click();
    });
  await expect(page.locator(".error-notice")).toContainText("Mất kết nối");
  await expect(page.locator(".metrics-model-pill").last()).toBeVisible();
  await expect(page.locator(".error-notice")).toHaveCount(0);
  expect(ids.length).toBe(1);
  expect(new Set(ids).size).toBe(1);
  const detail = await (
    await page.request.get(`/api/v1/sessions/${sessionId}`)
  ).json();
  expect(detail.messages).toHaveLength(2);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth))
    .toBe(390);
  await page.screenshot({
    path: testInfo.outputPath("preset-retry-mobile.png"),
    fullPage: true,
  });
});

test("provider auth failure preserves user login and exposes retry diagnostics", async ({
  page,
}) => {
  await login(page);
  await page.route("**/api/v1/chat", (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: {
          code: "PROVIDER_CONFIGURATION_ERROR",
          message: "Provider request failed",
          request_id: "test-provider-failure",
          retry_after_seconds: 125,
        },
      },
    }),
  );
  await page.route("**/api/v1/traces/test-provider-failure/calls", (route) =>
    route.fulfill({
      json: [
        {
          call_id: "test-call",
          model_id: "openai/gpt-oss-120b",
          error_code: "PROVIDER_CONFIGURATION_ERROR",
          upstream_status: 401,
          dispatch_state: "rejected",
          retry_after_seconds: 125,
        },
      ],
    }),
  );
  await page
    .getByRole("textbox", { name: "Nhập tin nhắn" })
    .fill("Provider fault test");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(page.locator(".error-notice")).toContainText(
    "chưa được cấu hình đúng",
  );
  await expect(page.locator(".error-notice")).toContainText("125");
  await page
    .getByText("Chi tiết các lần gọi dịch vụ AI", { exact: true })
    .click();
  await expect(page.locator(".error-notice")).toContainText(
    "openai/gpt-oss-120b",
  );
  await expect(
    page.getByRole("textbox", { name: "Nhập tin nhắn" }),
  ).toBeVisible();
  await expect(page.getByLabel("Tên đăng nhập", { exact: true })).toHaveCount(
    0,
  );
});

test("a proxy 500 recovers the actual backend timeout without a second POST", async ({
  page,
}) => {
  await login(page);
  let posts = 0;
  await page.route("**/api/v1/chat", (route) => {
    posts++;
    return route.fulfill({
      status: 500,
      json: { error: { code: "UNKNOWN", message: "Proxy failed" } },
    });
  });
  await page.route("**/api/v1/sessions/*/progress?**", (route) =>
    route.fulfill({
      json: { status: "failed", request_id: "failed-timeout", events: [] },
    }),
  );
  await page.route("**/api/v1/requests/failed-timeout/execution", (route) =>
    route.fulfill({
      json: {
        request_id: "failed-timeout",
        status: "failed",
        error_code: "PROVIDER_TIMEOUT",
        events: [],
        calls: [],
        legacy: false,
      },
    }),
  );
  await page.route("**/api/v1/traces/failed-timeout/calls", (route) =>
    route.fulfill({ json: [] }),
  );
  await page
    .getByRole("textbox", { name: "Nhập tin nhắn" })
    .fill("Giải thích VAE");
  await page.getByRole("button", { name: "Gửi tin nhắn" }).click();
  await expect(page.locator('.error-notice[role="alert"]')).toContainText(
    "Yêu cầu vượt thời gian xử lý",
  );
  await expect(page.locator('.error-notice[role="alert"]')).toContainText(
    "failed-timeout",
  );
  expect(posts).toBe(1);
  await expect(
    page.getByRole("textbox", { name: "Nhập tin nhắn" }),
  ).toHaveValue("Giải thích VAE");
});
