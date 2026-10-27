import {
  api,
  unwrap,
  ApiError,
  type ChatRequest,
  type ChatResponse,
} from "./api";

export function isTransportUncertain(error: unknown) {
  return (
    !(error instanceof ApiError) ||
    (error.code === "UNKNOWN" && error.status >= 500) ||
    error.code === "TRANSPORT_UNCERTAIN"
  );
}

type Recovery =
  | { status: "succeeded"; response: ChatResponse }
  | { status: "failed"; error: ApiError }
  | { status: "pending"; requestId?: string };

// Read-only recovery: never POST/replay a request whose dispatch is uncertain.
export async function recoverChat(request: ChatRequest): Promise<Recovery> {
  const progress = unwrap(
    await api.GET("/v1/sessions/{session_id}/progress", {
      params: {
        path: { session_id: request.session_id },
        query: { client_request_id: request.client_request_id },
      },
    }),
  );
  if (progress.status === "succeeded" && progress.request_id) {
    const response = unwrap(
      await api.GET("/v1/traces/{request_id}", {
        params: { path: { request_id: progress.request_id } },
      }),
    );
    return { status: "succeeded", response };
  }
  if (
    ["failed", "interrupted"].includes(progress.status) &&
    progress.request_id
  ) {
    const execution = unwrap(
      await api.GET("/v1/requests/{request_id}/execution", {
        params: { path: { request_id: progress.request_id } },
      }),
    );
    return {
      status: "failed",
      error: new ApiError(
        execution.error_code || "ATTEMPT_NOT_REPLAYABLE",
        execution.error_code === "PROVIDER_TIMEOUT" ? 504 : 502,
        progress.request_id,
      ),
    };
  }
  return { status: "pending", requestId: progress.request_id || undefined };
}
