/**
 * Test 1.2 — Bug Condition: Blocked Autoplay Does Not Show Prominent Play Button (Bug 2)
 *
 * Bug condition: VoiceAudioPlayer calls audio.play() inside a useEffect,
 * which runs outside a user-gesture context. Chrome/Firefox silently block
 * autoplay and reject the play() promise with a DOMException. The current
 * .catch handler only shows a small "Audio playback blocked — click to play."
 * text button — NOT a prominent "🔊 Tap to play" button.
 *
 * EXPECTED OUTCOME on unfixed code: FAILS
 * (only the "▶ Replay" link shown, NOT a button with name "tap to play")
 *
 * Validates: Requirements 1.2
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";

import VoiceAudioPlayer from "@/components/VoiceAudioPlayer";

// ── A valid tiny base64-encoded MP3 (just enough bytes to decode) ────────────
// "dGVzdA==" is base64 for "test" — not a real MP3 but enough for the test
// since we mock HTMLMediaElement.prototype.play anyway.
const TEST_AUDIO_B64 = "dGVzdA==";

describe("Bug 2 — Blocked autoplay does not show prominent play button", () => {
  let originalPlay: typeof HTMLMediaElement.prototype.play;
  let originalBody: typeof document.body.appendChild;

  beforeEach(() => {
    originalPlay = HTMLMediaElement.prototype.play;
    // Stub appendChild to prevent JSDOM errors with audio elements
    originalBody = document.body.appendChild.bind(document.body);

    // Stub load and pause to prevent JSDOM "Not implemented" errors
    Object.defineProperty(HTMLMediaElement.prototype, "load", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
    Object.defineProperty(HTMLMediaElement.prototype, "pause", {
      configurable: true,
      writable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    HTMLMediaElement.prototype.play = originalPlay;
    vi.restoreAllMocks();
  });

  it("shows a prominent 'Tap to play' button when autoplay is blocked by the browser", async () => {
    // Mock play() to simulate browser blocking autoplay
    const playPromise = Promise.reject(new DOMException("", "NotAllowedError"));
    playPromise.catch(() => {}); // prevent unhandled rejection warning
    HTMLMediaElement.prototype.play = vi.fn().mockReturnValue(playPromise);

    // Mock URL.createObjectURL and URL.revokeObjectURL (not in JSDOM)
    const mockObjectURL = "blob:mock-url";
    global.URL.createObjectURL = vi.fn().mockReturnValue(mockObjectURL);
    global.URL.revokeObjectURL = vi.fn();

    await act(async () => {
      render(<VoiceAudioPlayer audioB64={TEST_AUDIO_B64} autoPlay={true} />);
    });

    // Find the audio element and trigger "canplay" event to run autoplay flow
    const audioEl = document.querySelector("audio");
    expect(audioEl).toBeTruthy();
    await act(async () => {
      fireEvent(audioEl!, new Event("canplay"));
    });

    // On FIXED code: a prominent button with aria-label "Tap to play voice response"
    // or text "🔊 Tap to play" is rendered.
    await waitFor(() => {
      const tapToPlayButton = screen.getByRole("button", { name: /tap to play/i });
      expect(tapToPlayButton).toBeTruthy();
    });
  });

  it("does NOT show the 'Replay' button when autoplay is blocked (blocked state replaces replay)", async () => {
    const playPromise = Promise.reject(new DOMException("", "NotAllowedError"));
    playPromise.catch(() => {});
    HTMLMediaElement.prototype.play = vi.fn().mockReturnValue(playPromise);

    global.URL.createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    global.URL.revokeObjectURL = vi.fn();

    await act(async () => {
      render(<VoiceAudioPlayer audioB64={TEST_AUDIO_B64} autoPlay={true} />);
    });

    const audioEl = document.querySelector("audio");
    expect(audioEl).toBeTruthy();
    await act(async () => {
      fireEvent(audioEl!, new Event("canplay"));
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /tap to play/i })).toBeInTheDocument();
    });
  });
});
