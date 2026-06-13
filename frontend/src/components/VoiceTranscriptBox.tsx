"use client";

import { useEffect, useRef, useState } from "react";

export interface VoiceMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  audioB64?: string | null;   // TTS audio for assistant messages (realtime mode)
  audioFormat?: string | null; // MIME type for the audio (e.g., "audio/mpeg", "audio/L16;rate=24000")
  timestamp: Date;
}

interface VoiceTranscriptBoxProps {
  messages: VoiceMessage[];
  /**
   * "realtime"     — user turns are read-only chat bubbles; no editable input.
   * "transcription" — the last user-editable text is shown in a textarea below
   *                   the chat history; user can edit before submitting.
   */
  mode: "realtime" | "transcription";
  /** Current editable draft (transcription mode only). */
  draft?: string;
  /** Called when draft changes (transcription mode). */
  onDraftChange?: (text: string) => void;
  /** Called when user submits (both modes via Send button in transcription). */
  onSubmit?: (text: string) => void;
  /** Callback triggered when the assistant's voice audio finishes playing. */
  onAudioEnd?: () => void;
  /** Show a spinner in the last assistant slot while the agent is thinking. */
  agentThinking?: boolean;
  disabled?: boolean;
  className?: string;
}

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

/**
 * Compact waveform-only audio player for inside chat bubbles.
 * - No mic button, no replay control.
 * - Auto-plays on mount, shows animated bars while speaking.
 * - Fades out quietly when done.
 */
function InlineWaveformPlayer({
  audioB64,
  audioMimeType = "audio/mpeg",
  onEnded,
}: {
  audioB64: string;
  audioMimeType?: string;
  onEnded?: () => void;
}) {
  const [playing, setPlaying] = useState(false);
  // Keep onEnded stable in a ref so the effect closure doesn't go stale
  const onEndedRef = useRef(onEnded);
  useEffect(() => { onEndedRef.current = onEnded; }, [onEnded]);

  useEffect(() => {
    let audio: HTMLAudioElement | null = null;
    let objectUrl: string | null = null;
    let didEnd = false; // guard: ensure onEnded fires at most once
    let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

    const fireEnded = () => {
      if (fallbackTimer) {
        clearTimeout(fallbackTimer);
        fallbackTimer = null;
      }
      if (didEnd) return;
      didEnd = true;
      setPlaying(false);
      onEndedRef.current?.();
    };

    try {
      const bytes = Uint8Array.from(atob(audioB64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: audioMimeType });
      objectUrl = URL.createObjectURL(blob);
      audio = new Audio(objectUrl);
      audio.volume = 1.0;
      audio.preload = "auto";
      audio.style.display = "none";
      document.body.appendChild(audio);

      audio.onplay  = () => setPlaying(true);
      // Only treat pause as "ended" if audio actually finished
      audio.onended = fireEnded;
      audio.onerror = fireEnded;

      let loaded = false;
      const onCanPlay = () => {
        if (loaded) return;
        loaded = true;
        if (fallbackTimer) {
          clearTimeout(fallbackTimer);
          fallbackTimer = null;
        }
        audio!.play().catch((e: any) => {
          const isBlocked =
            e?.name === "NotAllowedError" ||
            e?.name === "AbortError" ||
            String(e?.message ?? "").includes("NotAllowedError");
          if (isBlocked) {
            // Give React a tick to render, then fire onEnded so
            // useVoiceSession transitions greeting/follow_up → listening.
            setTimeout(fireEnded, 100);
          } else {
            fireEnded();
          }
        });
      };

      audio.addEventListener("canplay", onCanPlay, { once: true });
      audio.load();

      // Safety fallback: if audio doesn't load/play in 2.5s (due to browser policy or load failure),
      // transition to listening so the user is not stuck.
      fallbackTimer = setTimeout(() => {
        if (!loaded) {
          console.warn("[InlineWaveformPlayer] Playback load timed out, transitioning.");
          fireEnded();
        }
      }, 2500);

    } catch { fireEnded(); }

    return () => {
      if (fallbackTimer) clearTimeout(fallbackTimer);
      if (audio) { audio.pause(); audio.parentNode?.removeChild(audio); }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioB64]);

  const durations = ["0.6s","0.9s","0.7s","1.1s","0.8s","1.0s","0.75s","0.85s","0.65s"];

  return (
    <div className="flex items-end gap-[2px] mt-2" style={{ height: 18 }} aria-hidden="true">
      {durations.map((dur, i) => (
        <span
          key={i}
          className={playing ? "animate-waveform-bar" : ""}
          style={{
            display: "inline-block",
            width: 2,
            height: 18,
            borderRadius: 9999,
            background: "linear-gradient(to top, #14b8a6, #e03e52)",
            ["--waveform-duration" as any]: dur,
            animationDelay: `${i * 55}ms`,
            transform: playing ? undefined : "scaleY(0.15)",
            transformOrigin: "bottom",
            transition: "transform 0.3s ease",
          }}
        />
      ))}
    </div>
  );
}

/**
 * Shared conversation UI used in both Real-Time and Transcription voice modes.
 *
 * Real-Time: read-only chat bubbles with inline TTS audio players.
 * Transcription: same chat bubbles + editable textarea + Send button at bottom.
 */
export default function VoiceTranscriptBox({
  messages,
  mode,
  draft = "",
  onDraftChange,
  onSubmit,
  onAudioEnd,
  agentThinking = false,
  disabled = false,
  className = "",
}: VoiceTranscriptBoxProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-scroll to newest message — scroll only within the box's own
  // overflow container, never the page. Use scrollTop on the container
  // directly instead of scrollIntoView (which can bubble up to the window).
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }, [messages, agentThinking]);

  const handleSend = () => {
    if (!draft.trim() || disabled) return;
    onSubmit?.(draft.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className={`flex flex-col rounded-2xl border border-gray-800 bg-[#111117]/80 backdrop-blur-md overflow-hidden ${className}`}
      aria-label="Voice conversation transcript"
    >
      {/* ── Chat history ── */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto p-4 space-y-3 max-h-72 min-h-[120px]"
      >
        {messages.length === 0 && (
          <p className="text-gray-500 text-sm text-center italic py-4">
            {mode === "realtime"
              ? "Start speaking to begin the conversation…"
              : "Tap the microphone to speak, then edit your message below."}
          </p>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex w-full ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div className={`flex gap-3 items-start ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}>
              {/* Avatar Circle */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-md ${
                    msg.role === "user"
                      ? "bg-[#e03e52] text-white"
                      : "bg-gray-800 text-[#e03e52] border border-gray-700"
                  }`}
                >
                  {msg.role === "user" ? "U" : "A"}
                </div>
                {msg.role === "assistant" && (
                  <span className="text-xs" title="Voice Mode">🎙️</span>
                )}
              </div>

              {/* Chat Bubble */}
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
                  msg.role === "user"
                    ? "bg-[#e03e52] text-white"
                    : "bg-gray-800 text-gray-200"
                }`}
              >
                <p className="text-sm leading-relaxed">{msg.content}</p>

                {/* Inline waveform-only player for assistant TTS — no mic, no replay */}
                {msg.role === "assistant" && msg.audioB64 && (
                  <InlineWaveformPlayer
                    audioB64={msg.audioB64}
                    audioMimeType={msg.audioFormat || "audio/mpeg"}
                    onEnded={onAudioEnd}
                  />
                )}

                <p className="text-[10px] opacity-50 mt-1 text-right">
                  {msg.timestamp.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </p>
              </div>
            </div>
          </div>
        ))}

        {/* Agent thinking indicator */}
        {agentThinking && (
          <div className="flex justify-start w-full">
            <div className="flex gap-3 items-start flex-row">
              {/* Avatar Circle */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shadow-md bg-gray-800 text-[#e03e52] border border-gray-700">
                  A
                </div>
                <span className="text-xs" title="Voice Mode">🎙️</span>
              </div>

              {/* Thinking Bubble */}
              <div className="bg-gray-800 text-gray-400 rounded-2xl px-4 py-2.5 flex items-center gap-2">
                <span className="text-sm">AI is thinking</span>
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </span>
              </div>
            </div>
          </div>
        )}


      </div>

      {/* ── Editable input (transcription mode only) ── */}
      {mode === "transcription" && (
        <div
          className="border-t border-gray-800 p-3 flex gap-2 items-end"
          style={{ background: "rgba(17,17,23,0.95)" }}
        >
          <textarea
            ref={textareaRef}
            rows={2}
            value={draft}
            onChange={(e) => onDraftChange?.(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Edit your message or speak again, then Send…"
            disabled={disabled}
            className="flex-1 bg-gray-900/80 border border-gray-700 rounded-xl px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-[#e03e52]/60 resize-none transition-colors"
            aria-label="Voice transcript — edit before submitting"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!draft.trim() || disabled}
            className="shrink-0 h-10 px-4 rounded-xl text-sm font-semibold transition-all disabled:opacity-40"
            style={{
              background: draft.trim() && !disabled ? "#e03e52" : "var(--bg-elevated)",
              color: "#fff",
            }}
            aria-label="Send message"
          >
            Send →
          </button>
        </div>
      )}
    </div>
  );
}
