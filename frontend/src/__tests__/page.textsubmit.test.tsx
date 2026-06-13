/**
 * Preservation Test 2.1 — Text submit path not affected.
 *
 * Validates: Requirements 3.1
 *
 * This test MUST PASS on unfixed code. It establishes the baseline that the
 * text-submit path (router.push with ?q=) works correctly and scrollY is unchanged.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

// ── Mocks ──────────────────────────────────────────────────────────────────

const mockRouterPush = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockRouterPush }),
}));

// Mock useVoiceSession — we don't want it to call the backend
vi.mock("@/hooks/useVoiceSession", () => ({
  useVoiceSession: () => ({
    state: "idle",
    messages: [],
    draft: "",
    error: null,
    isRecording: false,
    sessionId: null,
    setDraft: vi.fn(),
    startSession: vi.fn(),
    stopRecording: vi.fn(),
    submitDraft: vi.fn(),
  }),
}));

// Mock VoiceTranscriptBox — prevents rendering of inner voice components
vi.mock("@/components/VoiceTranscriptBox", () => ({
  default: () => <div data-testid="voice-transcript-box" />,
}));

// ── Import under test (after mocks are set up) ─────────────────────────────

import LandingPage from "@/app/page";

// ── Tests ──────────────────────────────────────────────────────────────────

describe("Preservation 2.1 — Text submit path not affected", () => {
  beforeEach(() => {
    mockRouterPush.mockClear();
    // Reset scrollY to 0 before each test
    Object.defineProperty(window, "scrollY", {
      configurable: true,
      writable: true,
      value: 0,
    });
  });

  it("calls router.push with ?q= param when text is submitted", () => {
    render(<LandingPage />);

    const textarea = screen.getByRole("textbox", { name: /trip request/i });
    fireEvent.change(textarea, {
      target: { value: "5 days in Paris for 2 people, $3000 budget" },
    });

    const submitButton = screen.getByRole("button", {
      name: /generate my travel plan/i,
    });
    fireEvent.click(submitButton);

    expect(mockRouterPush).toHaveBeenCalledTimes(1);
    const calledWith: string = mockRouterPush.mock.calls[0][0] as string;
    expect(calledWith).toMatch(/^\/?planner\?q=/);
    expect(calledWith).toContain("Paris");
  });

  it("scrollY remains 0 after text submit (no viewport jump)", () => {
    render(<LandingPage />);

    const scrollYBefore = window.scrollY;
    expect(scrollYBefore).toBe(0);

    const textarea = screen.getByRole("textbox", { name: /trip request/i });
    fireEvent.change(textarea, { target: { value: "Weekend trip to Tokyo" } });

    const submitButton = screen.getByRole("button", {
      name: /generate my travel plan/i,
    });
    fireEvent.click(submitButton);

    // scrollY must not change — text submit must not scroll the page
    expect(window.scrollY).toBe(0);
  });

  it("does not call router.push when query is empty", () => {
    render(<LandingPage />);

    const submitButton = screen.getByRole("button", {
      name: /generate my travel plan/i,
    });
    fireEvent.click(submitButton);

    expect(mockRouterPush).not.toHaveBeenCalled();
  });
});
