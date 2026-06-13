/**
 * Test 1.3 — Bug Condition: SSE 404 Shows Generic Error Instead of Session-Expired Message (Bug 3a)
 *
 * Bug condition: When openSSE calls onError with an error containing "HTTP 404"
 * (session expired), the PlannerPage shows a generic connection error message
 * instead of a user-friendly "Your voice session expired — please try again"
 * message with a "Go Back" navigation button.
 *
 * EXPECTED OUTCOME on unfixed code: FAILS
 * (generic error shown, not "voice session expired" text; no "Go Back" button)
 *
 * Validates: Requirements 1.4
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";

// ── Mock next/navigation ─────────────────────────────────────────────────────
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

// ── Mock openSSE to simulate SSE 404 error ───────────────────────────────────
// The SSE error must be: "SSE connection failed: HTTP 404" (from sse.ts)
let capturedOnError: ((err: Error) => void) | null = null;
vi.mock("@/lib/sse", () => ({
  openSSE: vi.fn((_path: string, options: { onError?: (err: Error) => void }) => {
    capturedOnError = options.onError ?? null;
    // Return a no-op cleanup function
    return () => {};
  }),
}));

// ── Mock @/lib/api ────────────────────────────────────────────────────────────
vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn().mockResolvedValue({}),
    get: vi.fn().mockResolvedValue({}),
  },
}));

// ── Mock child components that make additional requests ───────────────────────
vi.mock("@/components/VoiceInput", () => ({
  __esModule: true,
  default: () => <div data-testid="voice-input">VoiceInput</div>,
}));

vi.mock("@/components/VoiceAudioPlayer", () => ({
  __esModule: true,
  default: () => <div data-testid="voice-audio-player">VoiceAudioPlayer</div>,
}));

vi.mock("@/components/ChatInterface", () => ({
  __esModule: true,
  default: () => <div data-testid="chat-interface">ChatInterface</div>,
}));

vi.mock("@/components/PlanStatus", () => ({
  __esModule: true,
  default: () => <div data-testid="plan-status">PlanStatus</div>,
}));

// ── Import component under test ───────────────────────────────────────────────
import PlannerPage from "@/app/planner/page";

// ── Helper: inject a session_id into window.location.search for the test ─────
function setupSessionIdInUrl(sessionId: string) {
  Object.defineProperty(window, "location", {
    writable: true,
    configurable: true,
    value: {
      ...window.location,
      search: `?session_id=${sessionId}`,
    },
  });
}

describe("Bug 3a — SSE 404 shows generic error instead of session-expired message", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedOnError = null;
    mockPush.mockClear();

    // Mock window.history.replaceState to prevent errors
    Object.defineProperty(window, "history", {
      configurable: true,
      value: {
        ...window.history,
        replaceState: vi.fn(),
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(window, "location", {
      writable: true,
      configurable: true,
      value: {
        ...window.location,
        search: "",
      },
    });
  });

  it("displays 'voice session expired' message when SSE returns 404", async () => {
    /**
     * Bug condition:
     * - PlannerPage receives ?session_id=expired-id in URL
     * - openSSE is called → onError fires with "SSE connection failed: HTTP 404"
     * - The onError handler uses a generic fallback message
     *
     * Expected (FIXED behavior):
     * - Text matching /voice session expired/i is shown to the user
     *
     * Actual (UNFIXED behavior):
     * - The onError handler in runVoiceSessionPlan falls through to the generic
     *   message: "Connection error — your plan may still be generating."
     * - The test FAILS because /voice session expired/i text is NOT in the DOM.
     */
    setupSessionIdInUrl("expired-id");

    await act(async () => {
      render(<PlannerPage />);
    });

    // Now manually trigger the SSE 404 error (simulating the async network response)
    await act(async () => {
      if (capturedOnError) {
        capturedOnError(new Error("SSE connection failed: HTTP 404"));
      }
    });

    // On UNFIXED code: this assertion FAILS
    // The page shows "Connection error — your plan may still be generating."
    // NOT "Your voice session expired — please try again"
    await waitFor(() => {
      const voiceExpiredText = screen.queryByText(/voice session expired/i);
      expect(voiceExpiredText).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows a 'Go Back' button when SSE 404 session-expired error occurs", async () => {
    /**
     * Bug condition: same as above.
     *
     * Expected (FIXED behavior):
     * - A button with text/label matching /go back/i is shown
     *
     * Actual (UNFIXED behavior):
     * - No "Go Back" button is rendered — test FAILS
     */
    setupSessionIdInUrl("expired-id");

    await act(async () => {
      render(<PlannerPage />);
    });

    // Trigger the SSE 404 error
    await act(async () => {
      if (capturedOnError) {
        capturedOnError(new Error("SSE connection failed: HTTP 404"));
      }
    });

    // On UNFIXED code: this assertion FAILS — no Go Back button rendered
    await waitFor(() => {
      const goBackButton = screen.queryByRole("button", { name: /go back/i });
      expect(goBackButton).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
