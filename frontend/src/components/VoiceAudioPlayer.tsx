"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface VoiceAudioPlayerProps {
  /** Base64-encoded audio bytes. When null the mic is shown in "waiting" state. */
  audioB64: string | null;
  /** Audio MIME type. */
  audioMimeType?: string;
  /** Auto-play as soon as audioB64 arrives. Default true. */
  autoPlay?: boolean;
  /** Called when playback finishes. */
  onEnded?: () => void;
  className?: string;
  /** Label shown under the mic while audio isn't ready yet. */
  waitingLabel?: string;
}

/**
 * Voice mic button that mirrors the landing page design.
 *
 * States:
 *  • waiting  – audioB64 is null.  Mic pulsates softly, label shows waitingLabel.
 *  • ready    – audioB64 arrived, not yet played.  Mic glows accent, "Tap to listen".
 *  • blocked  – browser blocked autoplay.  Same as ready but more prominent.
 *  • playing  – audio is playing.  Waveform bars animate under the mic, "Speaking…"
 *  • done     – playback finished.  Mic neutral, "▶ Tap to replay".
 *  • error    – decode/play failed.  Mic amber, "⚠ Tap to retry".
 */
export default function VoiceAudioPlayer({
  audioB64,
  audioMimeType = "audio/mpeg",
  autoPlay = true,
  onEnded,
  className = "",
  waitingLabel = "Planning your trip…",
}: VoiceAudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef   = useRef<string | null>(null);

  type PlayerState = "waiting" | "ready" | "blocked" | "playing" | "error";
  const [state, setState] = useState<PlayerState>("waiting");

  // ── play() ─────────────────────────────────────────────────────────────
  const play = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.currentTime && audio.ended) audio.currentTime = 0;
    audio.play().catch((e: any) => {
      const name    = e?.name    ?? "";
      const message = e?.message ?? "";
      if (
        name === "NotAllowedError" ||
        name === "AbortError"      ||
        message.includes("NotAllowedError") ||
        message.includes("user didn't interact")
      ) {
        setState("blocked");
      } else {
        setState("error");
      }
      console.warn("VoiceAudioPlayer play() rejected:", e);
    });
  }, []);

  // ── Load audio when audioB64 changes ───────────────────────────────────
  useEffect(() => {
    if (!audioB64) {
      setState("waiting");
      return;
    }

    setState("ready");

    let audio: HTMLAudioElement | null = null;
    let objectUrl: string | null = null;

    try {
      const bytes = Uint8Array.from(atob(audioB64), (c) => c.charCodeAt(0));
      const blob  = new Blob([bytes], { type: audioMimeType });
      objectUrl   = URL.createObjectURL(blob);
      urlRef.current = objectUrl;

      audio = new Audio(objectUrl);
      audioRef.current = audio;

      audio.style.display = "none";
      document.body.appendChild(audio);
      audio.volume  = 1.0;
      audio.preload = "auto";

      audio.onplay  = () => setState("playing");
      audio.onpause = () => setState((s) => s === "playing" ? "ready" : s);
      audio.onended = () => { setState("ready"); onEnded?.(); };
      audio.onerror = () => { setState("error"); onEnded?.(); };

      if (autoPlay) {
        audio.addEventListener("canplay", play, { once: true });
        audio.load();
      }
    } catch (e) {
      setState("error");
      console.error("VoiceAudioPlayer decode error:", e);
    }

    return () => {
      if (audio) {
        audio.removeEventListener("canplay", play);
        audio.pause();
        if (audio.parentNode) audio.parentNode.removeChild(audio);
      }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      urlRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioB64]);

  // ── Derive mic button appearance ────────────────────────────────────────
  const isPlaying  = state === "playing";
  const isWaiting  = state === "waiting";
  const isReady    = state === "ready" || state === "blocked";
  const isError    = state === "error";

  // Colors & shadow classes (completely matching landing page consistency)
  const buttonStateClass = isWaiting
    ? "bg-[#8B0000] border-[#8B0000] shadow-[0_4px_16px_rgba(139,0,0,0.25)]"
    : isReady
    ? "bg-[#8B0000] border-[#8B0000] hover:bg-[#A52A2A] hover:shadow-[0_0_25px_rgba(139,0,0,0.4)] shadow-[0_0_28px_rgba(139,0,0,0.45)] hover:scale-105 active:scale-95"
    : isPlaying
    ? "bg-green-600 border-green-500 shadow-[0_0_28px_rgba(22,163,74,0.5)] hover:scale-105 active:scale-95"
    : /* error */
      "bg-[#92400e] border-[#92400e] shadow-[0_0_20px_rgba(146,64,14,0.4)] hover:scale-105 active:scale-95";

  const micEmoji = isWaiting  ? "🎙️"
    : isReady              ? "🎙️"
    : isPlaying            ? "🔊"
    : "⚠️";

  const micLabel = isWaiting  ? waitingLabel
    : isReady              ? "Tap to listen"
    : isPlaying            ? "Speaking…"
    : "⚠ Tap to retry";

  const micLabelColor = isWaiting  ? "var(--text-muted)"
    : isReady              ? "#e03e52"
    : isPlaying            ? "#4ade80"
    : "#f59e0b";

  // Which pulse animation class to apply
  const pulseClass = isWaiting  ? "voice-mic-pulse-idle"
    : isReady              ? "voice-mic-pulse-ready"
    : "";

  const handleMicClick = () => {
    if (isWaiting) return; // nothing to play yet
    if (isPlaying) {
      const audio = audioRef.current;
      if (audio) {
        audio.pause();
        audio.currentTime = 0; // stop and reset to beginning
      }
      setState("ready");
    } else {
      play();
    }
  };

  return (
    <div
      className={`flex flex-col items-center gap-4 ${className}`}
      aria-label="Voice response audio"
    >
      {/* ── Mic button (always rendered) ── */}
      <div className="relative flex items-center justify-center">
        {/* Ping ring when recording / speaking */}
        {isPlaying && (
          <span
            className="absolute inset-0 rounded-2xl border-2 border-green-400 animate-ping opacity-75"
            style={{ borderRadius: 16 }}
          />
        )}
        {/* Ready glow ring */}
        {isReady && (
          <span
            className="absolute inset-0 animate-pulse opacity-50"
            style={{
              borderRadius: 16,
              boxShadow: "0 0 0 6px rgba(224,62,82,0.25)",
            }}
          />
        )}
        {/* Idle soft pulse ring */}
        {isWaiting && (
          <span
            className="absolute inset-0 opacity-30"
            style={{
              borderRadius: 16,
              animation: "voice-idle-pulse 2.5s ease-in-out infinite",
              boxShadow: "0 0 0 8px rgba(255,255,255,0.06)",
            }}
          />
        )}

        <button
          type="button"
          onClick={handleMicClick}
          onMouseDown={(e) => e.preventDefault()}
          aria-label={isWaiting ? "Preparing audio…" : isPlaying ? "Playing audio" : "Tap to play voice summary"}
          aria-pressed={isPlaying}
          className={`relative flex h-20 w-20 items-center justify-center rounded-2xl text-4xl border ${buttonStateClass} ${pulseClass} ${
            isWaiting ? "cursor-not-allowed" : "cursor-pointer"
          }`}
          style={{
            borderWidth: 1,
            color: "#fff",
            transition: "transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.3s ease, box-shadow 0.3s ease, opacity 0.3s ease",
          }}
        >
          {micEmoji}
        </button>
      </div>

      {/* ── Waveform bars (visible while playing) ── */}
      <div
        className="flex items-end gap-[3px]"
        style={{ height: 32, opacity: isPlaying ? 1 : 0.18, transition: "opacity 0.4s ease" }}
        aria-hidden="true"
      >
        {Array.from({ length: 9 }, (_, i) => {
          const durations = ["0.6s","0.9s","0.7s","1.1s","0.8s","1.0s","0.75s","0.85s","0.65s"];
          return (
            <span
              key={i}
              className={isPlaying ? "animate-waveform-bar" : ""}
              style={{
                width: 3,
                height: 32,
                borderRadius: 9999,
                background: "linear-gradient(to top, #14b8a6, #e03e52)",
                animationDelay: `${i * 55}ms`,
                ["--waveform-duration" as any]: durations[i],
                transform: isPlaying ? undefined : "scaleY(0.18)",
                transformOrigin: "bottom",
                transition: "transform 0.4s ease",
              }}
            />
          );
        })}
      </div>

      {/* ── Label under mic ── */}
      <span
        className="text-xs font-bold tracking-wider uppercase"
        style={{ color: micLabelColor, transition: "color 0.3s ease" }}
      >
        {micLabel}
      </span>
    </div>
  );
}
