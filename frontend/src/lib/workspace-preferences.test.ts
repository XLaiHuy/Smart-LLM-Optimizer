import { describe, expect, it } from "vitest";
import {
  parseChatPreferences,
  shouldPollDocumentJobs,
} from "./workspace-preferences";

describe("workspace preferences", () => {
  it("accepts only supported chat modes", () => {
    expect(
      parseChatPreferences('{"mode":"baseline","candidate":"groq"}'),
    ).toEqual({ mode: "baseline", candidate: "groq" });
    expect(parseChatPreferences('{"mode":"other"}')).toBeNull();
    expect(parseChatPreferences("not-json")).toBeNull();
  });

  it("polls document jobs only while work is active", () => {
    expect(shouldPollDocumentJobs(undefined)).toBe(false);
    expect(shouldPollDocumentJobs([])).toBe(false);
    expect(shouldPollDocumentJobs([{ status: "succeeded" }])).toBe(false);
    expect(shouldPollDocumentJobs([{ status: "pending" }])).toBe(1000);
    expect(shouldPollDocumentJobs([{ status: "running" }])).toBe(1000);
  });
});
