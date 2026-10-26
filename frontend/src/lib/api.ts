import createClient from "openapi-fetch";
import type { paths, components } from "./generated/api";

export const api = createClient<paths>({
  baseUrl: "/api",
  credentials: "same-origin",
});
api.use({
  onResponse({ request, response }) {
    if (
      response.status === 401 &&
      !request.url.includes("/auth/") &&
      typeof window !== "undefined"
    ) {
      window.dispatchEvent(new Event("auth-expired"));
    }
    return response;
  },
});
export type User = components["schemas"]["Principal"];
export type ChatResponse = components["schemas"]["ChatResponse"];
export type ChatRequest = components["schemas"]["ChatRequest"];
export type SessionInfo = components["schemas"]["SessionInfo"];
export type SessionDetail = components["schemas"]["SessionDetail"];
export type Overview = components["schemas"]["Overview"];
export type Flags = Required<components["schemas"]["FeatureFlags"]>;

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number = 0,
  ) {
    super(code);
  }
}

export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error || !result.response.ok) {
    const error = result.error as
      components["schemas"]["ErrorEnvelope"] | undefined;
    throw new ApiError(error?.error?.code || "UNKNOWN", result.response.status);
  }
  return result.data as T;
}

export const allFlags: Flags = {
  router: true,
  rewrite: true,
  context: true,
  memory: true,
};
export function requestFlags(
  mode: "baseline" | "optimized",
  flags: Flags,
): Flags {
  return mode === "baseline" ? { ...flags, router: false } : { ...flags };
}
