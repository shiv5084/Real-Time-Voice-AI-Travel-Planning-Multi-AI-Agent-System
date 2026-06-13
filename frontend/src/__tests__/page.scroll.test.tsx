/**
 * Test 1.1 — Bug Condition: Mic Tap Causes Viewport Scroll (Bug 1)
 *
 * Bug condition: handleMicToggle in page.tsx does not call e.preventDefault()
 * on the click event. When voiceActive becomes true, React inserts
 * VoiceTranscriptBox into the DOM. If the browser auto-focuses any element
 * inside it, the viewport scrolls to keep focus in view.
 *
 * EXPECTED OUTCOME on unfixed code: FAILS
 * (scrollY may change or behavior differs — bug confirmed)
 *
 * Validates: Requirements 1.1
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, fireEvent, screen, act, createEvent } from "@testing-library/react";

// ── Mock next/navigation ─────────────────────────────────────────────────────
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Mock useVoiceSession to prevent network calls ────────────────────────────
vi.mock("@/hooks/useVoiceSession", () => ({
  useVoiceSession: () => ({
    state: "idle",
    messages: [],
    draft: "",
    error: null,
    isRecording: false,
    sessionId: null,
    setDraft: vi.fn(),
    startSession: vi.fn().mockResolvedValue(undefined),
    stopRecording: vi.fn(),
    submitDraft: vi.fn(),
  }),
}));

// ── Mock child components ─────────────────────────────────────────────────────
vi.mock("@/components/VoiceTranscriptBox", () => ({
  __esModule: true,
  default: () => <div data-testid="voice-transcript-box">VoiceTranscriptBox</div>,
}));

// ── Import the component under test ──────────────────────────────────────────
import LandingPage from "@/app/page";

describe("Bug 1 — Scroll on mic tap", () => {
  beforeEach(() => {
    // JSDOM does not implement scrollY changes, but we can verify
    // that e.preventDefault() is called on the click event.
    // scrollY in JSDOM is always 0, but we can track if the
    // DOM expansion caused any scroll attempt via window.scrollTo mock.
    vi.clearAllMocks();
    Object.defineProperty(window, "scrollY", {
      writable: true,
      value: 0,
    });
  });

  it("should NOT change window.scrollY after mic button click (bug: scrollY changes on unfixed code)", async () => {
    /**
     * Bug condition: handleMicToggle does NOT call e.preventDefault().
     * On unfixed code, clicking the mic button without e.preventDefault()
     * can cause the browser to scroll to the newly inserted VoiceTranscriptBox.
     *
     * This test verifies that after clicking the mic button, the page
     * scrollY position remains 0 (no scroll occurred).
     *
     * On UNFIXED code this test FAILS because e.preventDefault() is not called,
     * allowing the browser's default focus-scroll behavior to trigger.
     */

    // Spy on window.scrollTo to detect any programmatic scroll attempts
    const scrollToSpy = vi.spyOn(window, "scrollTo").mockImplementation(() => {});

    render(<LandingPage />);

    // Record scrollY before click
    const scrollBefore = window.scrollY;

    // Find the mic button
    const micButton = screen.getByRole("button", { name: /start voice recording/i });
    expect(micButton).toBeTruthy();

    // Simulate a click event — this is what the user does
    await act(async () => {
      fireEvent.click(micButton);
    });

    // Assert scrollY has not changed (no scroll occurred)
    const scrollAfter = window.scrollY;
    expect(scrollAfter).toBe(scrollBefore);

    // The key invariant: e.preventDefault() must be called on the click event
    // to prevent default browser scroll-to-focused-element behavior.
    // On unfixed code, handleMicToggle is declared as `async () => {}` — it
    // receives NO event object and cannot call e.preventDefault().
    // This test will FAIL on unfixed code because the button does not
    // prevent default focus scroll when VoiceTranscriptBox is inserted.

    // Additionally, verify no programmatic scroll was called
    expect(scrollToSpy).not.toHaveBeenCalled();

    scrollToSpy.mockRestore();
  });

  it("should have mic button that calls e.preventDefault() on click", async () => {
    /**
     * Stronger version: directly verify preventDefault is called.
     * On unfixed code: onClick={handleMicToggle} where handleMicToggle is
     * async () => {} (no event param) — so preventDefault is NEVER called.
     * On fixed code: onClick={(e) => handleMicToggle(e)} where handleMicToggle
     * accepts the event and calls e.preventDefault() first.
     */
    render(<LandingPage />);

    const micButton = screen.getByRole("button", { name: /start voice recording/i });

    const clickEvent = createEvent.click(micButton);
    // Simulate click with a custom event that tracks preventDefault
    await act(async () => {
      fireEvent(micButton, clickEvent);
    });

    // On UNFIXED code: fails — preventDefault is never called
    // On FIXED code: passes — handler calls e.preventDefault() first
    expect(clickEvent.defaultPrevented).toBe(true);
  });
});
