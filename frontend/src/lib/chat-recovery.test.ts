import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, type ChatRequest, CHAT_DEADLINE_MS } from "./api";
import { recoverChat, isTransportUncertain } from "./chat-recovery";

const request: ChatRequest = {
  session_id: "s",
  client_request_id: "client-1",
  message: "code",
  mode: "optimized",
  document_ids: [],
};
const result = (data: unknown) => ({
  data,
  response: new Response(null, { status: 200 }),
});
afterEach(() => vi.restoreAllMocks());
describe("read-only chat recovery", () => {
  it("recovers a committed response without another POST", async () => {
    const replies = [
      result({ status: "succeeded", request_id: "r" }),
      result({ request_id: "r", response: { content: "saved" } }),
    ];
    const get = vi
      .spyOn(api, "GET")
      .mockImplementation(async () => replies.shift() as never);
    const post = vi.spyOn(api, "POST");
    const recovered = await recoverChat(request);
    expect(recovered.status).toBe("succeeded");
    if (recovered.status === "succeeded")
      expect(recovered.response.response.content).toBe("saved");
    expect(get.mock.calls.map((c) => c[0])).toEqual([
      "/v1/sessions/{session_id}/progress",
      "/v1/traces/{request_id}",
    ]);
    expect(post).not.toHaveBeenCalled();
  });
  it("preserves the server failure and owned request id", async () => {
    const replies = [
      result({ status: "failed", request_id: "r" }),
      result({ error_code: "PROVIDER_TIMEOUT" }),
    ];
    vi.spyOn(api, "GET").mockImplementation(
      async () => replies.shift() as never,
    );
    const post = vi.spyOn(api, "POST");
    const recovered = await recoverChat(request);
    expect(recovered.status).toBe("failed");
    if (recovered.status === "failed") {
      expect(recovered.error.code).toBe("PROVIDER_TIMEOUT");
      expect(recovered.error.requestId).toBe("r");
    }
    expect(post).not.toHaveBeenCalled();
  });
  it.each(["running", "pending"])(
    "does not retry or infer completion from %s",
    async (status) => {
      const get = vi
        .spyOn(api, "GET")
        .mockResolvedValue(result({ status, request_id: "r" }) as never);
      const post = vi.spyOn(api, "POST");
      expect((await recoverChat(request)).status).toBe("pending");
      expect(get).toHaveBeenCalledTimes(1);
      expect(post).not.toHaveBeenCalled();
    },
  );
  it("failed status reads do not authorize provider calls", async () => {
    vi.spyOn(api, "GET").mockRejectedValue(new TypeError("offline"));
    const post = vi.spyOn(api, "POST");
    await expect(recoverChat(request)).rejects.toThrow("offline");
    expect(post).not.toHaveBeenCalled();
  });
  it("distinguishes transport uncertainty from known quota or auth errors", () => {
    expect(isTransportUncertain(new ApiError("UNKNOWN", 500))).toBe(true);
    expect(isTransportUncertain(new TypeError("socket reset"))).toBe(true);
    expect(isTransportUncertain(new ApiError("RATE_LIMITED", 429))).toBe(false);
    expect(isTransportUncertain(new ApiError("AUTH_REQUIRED", 401))).toBe(
      false,
    );
    expect(isTransportUncertain(new ApiError("PROVIDER_TIMEOUT", 504))).toBe(
      false,
    );
  });
  it("keeps the interactive deadline inside the backend ceiling", () => {
    expect(CHAT_DEADLINE_MS).toBe(120000);
  });
});
