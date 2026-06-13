"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { VoiceClient, type VoiceStatus } from "@/lib/voice";

interface VoiceInputProps {
  /** Called with the final (possibly edited) transcript text. */
  onTranscriptReady: (text: string) => void;
  /** Called with the raw audio blob for STT if you want server-side transcription. */
  onAudioReady?: (blob: Blob, mimeType: string) => void;
  disabled?: boolean;
  className?: string;
}

const STATUS_LABEL: Record<VoiceStatus, string> = {
  idle:                 "Click to speak",
  requesting_permission: "Requesting microphone…",
  listening:            "Listening…",
  recording:            "Recording…",
  processing:           "Processing audio…",
  error:                "Microphone error",
};

const STATUS_COLOR: Record<VoiceStatus, string> = {
  idle:                 "var(--text-muted)",
  requesting_permission: "var(--warning)",
  listening:            "var(--accent)",
  recording:            "var(--success)",
  processing:           "var(--info)",
  error:                "var(--error)",
};

export default function VoiceInput({
  onTranscriptReady,
  onAudioReady,
  disabled = false,
  className = "",
}: VoiceInputProps) {
  const [status, setStatus]       = useState<VoiceStatus>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError]         = useState<string | null>(null);
  const clientRef = useRef<VoiceClient | null>(null);

  // Initialise VoiceClient
  useEffect(() => {
    clientRef.current = new VoiceClient({
      onAudioReady: (blob, mimeType) => {
        onAudioReady?.(blob, mimeType);
      },
      onStatusChange: setStatus,
      onError: (err) => setError(err.message),
      silenceThresholdMs: 2000,
    });

    return () => {
      clientRef.current?.destroy();
    };
  }, [onAudioReady]);

  const handleToggle = useCallback(async () => {
    if (disabled) return;
    setError(null);
    const client = clientRef.current;
    if (!client) return;

    if (client.currentStatus === "idle") {
      await client.start();
    } else {
      client.stop();
    }
  }, [disabled]);

  const handleSubmit = () => {
    if (transcript.trim()) {
      onTranscriptReady(transcript.trim());
      setTranscript("");
    }
  };

  const isActive = status === "listening" || status === "recording";

  return (
    <div className={`flex flex-col gap-3 ${className}`} aria-label="Voice input">
      {/* Mic button */}
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={handleToggle}
          onMouseDown={(e) => e.preventDefault()}
          disabled={disabled || status === "requesting_permission" || status === "processing"}
          aria-label={isActive ? "Stop recording" : "Start voice recording"}
          aria-pressed={isActive}
          className="btn relative flex h-14 w-14 items-center justify-center rounded-full text-2xl"
          style={{
            background:   isActive ? "var(--success)" : "var(--bg-elevated)",
            border:       `2px solid ${isActive ? "var(--success)" : "var(--border)"}`,
            color:        isActive ? "#fff" : "var(--text-secondary)",
            boxShadow:    isActive ? "var(--shadow-glow)" : "none",
          }}
        >
          {/* Pulse ring when active */}
          {isActive && (
            <span
              aria-hidden="true"
              className="animate-pulse-ring absolute inset-0 rounded-full"
            />
          )}
          {status === "processing" ? "⏳" : isActive ? "⏹" : "🎙️"}
        </button>

        <div>
          <p
            className="text-sm font-medium"
            style={{ color: STATUS_COLOR[status] }}
            aria-live="polite"
          >
            {STATUS_LABEL[status]}
          </p>
          {error && (
            <p className="text-xs" style={{ color: "var(--error)" }} role="alert">
              {error}
            </p>
          )}
        </div>
      </div>

      {/* Editable transcript */}
      <div className="flex flex-col gap-2">
        <label htmlFor="voice-transcript" className="text-xs" style={{ color: "var(--text-muted)" }}>
          Transcript (edit before submitting)
        </label>
        <textarea
          id="voice-transcript"
          rows={3}
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          placeholder="Your speech will appear here…"
          className="input resize-none text-sm"
          aria-label="Voice transcript"
          style={{ fontFamily: "var(--font-sans)" }}
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={!transcript.trim()}
          className="btn btn-primary self-end"
          aria-label="Submit transcript"
        >
          Send →
        </button>
      </div>
    </div>
  );
}
