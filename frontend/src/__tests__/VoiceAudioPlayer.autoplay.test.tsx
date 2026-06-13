/**
 * Preservation Test 2.2 — Autoplay succeeds when not blocked.
 *
 * Validates: Requirements 3.2
 *
 * This test MUST PASS on unfixed code. It establishes the baseline that when
 * autoplay is allowed by the browser, no "Tap to play" button is shown.
 * The component either shows "Speaking…" (if playing) or "▶ Replay" (after
 * play resolves but onplay hasn't fired in jsdom), but NEVER "Tap to play".
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";
import VoiceAudioPlayer from "@/components/VoiceAudioPlayer";

// ── Minimal valid base64 payload ───────────────────────────────────────────
// base64("test") — enough bytes for the component to create a Blob
const VALID_AUDIO_B64 = "dGVzdA==";

// ── Setup / Teardown ───────────────────────────────────────────────────────

beforeEach(() => {
  // Provide a stub URL so URL.createObjectURL doesn't throw in jsdom
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: vi.fn().mockReturnValue("blob:mock"),
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });

  // Mock play() to resolve immediately — autoplay is NOT blocked
  Object.defineProperty(HTMLMediaElement.prototype, "play", {
    configurable: true,
    writable: true,
    value: vi.fn().mockResolvedValue(undefined),
  });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", {
    configurable: true,
    writable: true,
    value: vi.fn(),
  });

  // Stub appendChild/removeChild on document.body to prevent test contamination
  // Only stub after React has had a chance to render into the document
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ──────────────────────────────────────────────────────────────────

describe("Preservation 2.2 — Autoplay succeeds when not blocked", () => {
  it("does NOT render a Tap-to-play button when autoplay resolves", async () => {
    render(<VoiceAudioPlayer audioB64={VALID_AUDIO_B64} autoPlay={true} />);

    // Give play() time to resolve
    await waitFor(() => {
      const tapToPlay = screen.queryByRole("button", { name: /tap to play/i });
      expect(tapToPlay).toBeNull();
    });
  });

  it("renders the voice response container with correct aria-label", async () => {
    render(<VoiceAudioPlayer audioB64={VALID_AUDIO_B64} autoPlay={true} />);

    // The component should render the outer wrapper (not be null)
    await waitFor(() => {
      const container = screen.queryByLabelText("Voice response audio");
      // The component renders when audioB64 is set; confirm aria-label is present
      expect(container).not.toBeNull();
    });
  });

  it("shows Replay button or Speaking span — but never Tap-to-play", async () => {
    render(<VoiceAudioPlayer audioB64={VALID_AUDIO_B64} autoPlay={true} />);

    await waitFor(() => {
      // "Tap to play" must NOT be present
      expect(screen.queryByRole("button", { name: /tap to play/i })).toBeNull();

      // Either the Replay button or the Speaking text is present
      const replayBtn = screen.queryByRole("button", { name: /replay/i });
      const speakingSpan = screen.queryByText(/speaking/i);
      expect(replayBtn !== null || speakingSpan !== null).toBe(true);
    });
  });

  it("returns null when audioB64 is null", () => {
    const { container } = render(
      <VoiceAudioPlayer audioB64={null} autoPlay={true} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
