/**
 * useVoiceSession — Voice state machine hook
 *
 * Manages the full lifecycle of a voice conversation:
 *   IDLE → GREETING → LISTENING → PROCESSING → AGENT_THINKING
 *          → FOLLOW_UP → LISTENING → … (loop)
 *          → READY_TO_REDIRECT
 *
 * Works for both modes:
 *   "realtime"     — transcripts auto-submitted; TTS audio played automatically
 *   "transcription" — transcript placed in editable draft; user submits manually
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { VoiceClient } from "@/lib/voice";
import type { VoiceMessage } from "@/components/VoiceTranscriptBox";

// ── Types ─────────────────────────────────────────────────────────────────

export type VoiceSessionState =
  | "idle"
  | "greeting"
  | "listening"
  | "processing"      // audio being transcribed
  | "agent_thinking"  // reply sent, waiting for server response
  | "follow_up"       // server returned a follow-up question
  | "ready"           // all info collected → redirect
  | "error";

export type VoiceMode = "realtime" | "transcription";

interface UseVoiceSessionOptions {
  mode: VoiceMode;
  onReady: (sessionId: string, messages: VoiceMessage[]) => void;  // called when redirect should happen
}

interface UseVoiceSessionReturn {
  state: VoiceSessionState;
  messages: VoiceMessage[];
  draft: string;                          // editable draft (transcription mode)
  error: string | null;
  isRecording: boolean;
  sessionId: string | null;
  setDraft: (text: string) => void;
  startSession: () => Promise<void>;      // tap mic
  stopRecording: () => void;             // manual stop
  submitDraft: () => Promise<void>;      // transcription mode — Send button
  reset: () => void;                     // discard session, return to idle
  onAudioEnd: () => Promise<void>;        // audio playback complete callback
  initAudioContext?: () => void;         // initialize AudioContext on user gesture
}

// Use a relative base URL so all API calls go through the Next.js /api rewrite
// proxy (next.config.ts). This avoids direct cross-origin requests to the
// backend and eliminates CORS issues in development.
// NEXT_PUBLIC_API_URL is only used as a fallback for server-side rendering
// or Docker environments where the proxy is not available.
const API_URL =
  typeof window !== "undefined"
    ? "" // browser: use relative URLs → proxied by Next.js dev server
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"); // SSR

function makeId() {
  return Math.random().toString(36).slice(2, 10);
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useVoiceSession({
  mode,
  onReady,
}: UseVoiceSessionOptions): UseVoiceSessionReturn {
  const [state, setState]       = useState<VoiceSessionState>("idle");
  const [messages, setMessages] = useState<VoiceMessage[]>([]);
  const [draft, setDraft]       = useState("");
  const [error, setError]       = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [sessionId, setSessionId]     = useState<string | null>(null);

  const voiceClientRef    = useRef<VoiceClient | null>(null);
  const sessionIdRef      = useRef<string | null>(null);
  const autoListenTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autoListenEnabledRef = useRef(true);
  const sessionTokenRef   = useRef<string | null>(null);

  // Keep sessionIdRef in sync
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const messagesRef = useRef<VoiceMessage[]>([]);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // ── VoiceClient initialisation ──────────────────────────────────────

  useEffect(() => {
    voiceClientRef.current = new VoiceClient({
      silenceThresholdMs: 2500,
      onStatusChange: (s) => {
        setIsRecording(s === "listening" || s === "recording");
      },
      onError: (err) => {
        setError(`Microphone error: ${err.message}. Please type your request.`);
        setState("error");
        setIsRecording(false);
      },
      onAudioReady: async (blob, mimeType) => {
        const token = sessionTokenRef.current;
        if (!token) return;

        // Transcribe the captured audio
        setState("processing");
        setIsRecording(false);

        let extension = "webm";
        const mimeTypeLower = mimeType.toLowerCase();
        if (mimeTypeLower.includes("mp4") || mimeTypeLower.includes("m4a")) {
          extension = "mp4";
        } else if (mimeTypeLower.includes("webm")) {
          extension = "webm";
        } else if (mimeTypeLower.includes("ogg")) {
          extension = "ogg";
        } else if (mimeTypeLower.includes("wav")) {
          extension = "wav";
        } else if (mimeTypeLower.includes("mpeg") || mimeTypeLower.includes("mp3")) {
          extension = "mp3";
        } else {
          const part = mimeType.split(";")[0]?.split("/")[1];
          if (part) extension = part;
        }

        const formData = new FormData();
        formData.append("audio", blob, `recording.${extension}`);

        try {
          const resp = await fetch(`${API_URL}/api/voice/transcribe`, {
            method: "POST",
            body: formData,
          });
          if (sessionTokenRef.current !== token) return;

          if (!resp.ok) throw new Error(`STT failed: HTTP ${resp.status}`);
          const data = await resp.json();

          if (data.fallback_to_text || !data.transcript) {
            // STT returned nothing — show error but keep session alive
            setError("No speech detected — please try again or type below.");
            setState(mode === "transcription" ? "follow_up" : "listening");
            return;
          }

          const transcript: string = data.transcript;

          if (mode === "realtime") {
            // Append user bubble and auto-submit to server
            appendMessage("user", transcript, null);
            await submitToServer(transcript);
          } else {
            // Transcription mode — put in editable draft
            setDraft(transcript);
            setState("follow_up");
          }
        } catch (e: unknown) {
          if (sessionTokenRef.current !== token) return;
          const msg = e instanceof Error ? e.message : "Transcription failed";
          setError(`${msg} — please type your request.`);
          setState("error");
        }
      },
    });

    return () => {
      voiceClientRef.current?.destroy();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // ── Helpers ──────────────────────────────────────────────────────────

  const appendMessage = useCallback(
    (
      role: "user" | "assistant",
      content: string,
      audioB64: string | null,
      audioFormat?: string | null,
    ) => {
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role, content, audioB64, audioFormat, timestamp: new Date() },
      ]);
    },
    [],
  );

  /** Send one user turn to the backend and handle the response. */
  const submitToServer = useCallback(
    async (transcript: string) => {
      const token = sessionTokenRef.current;
      const sid = sessionIdRef.current;
      if (!sid) {
        // If the session was cancelled/reset, degrade gracefully and exit silently
        if (!token) return;

        setError("Session not initialised. Please restart.");
        setState("error");
        return;
      }

      setState("agent_thinking");

      try {
        const resp = await fetch(`${API_URL}/api/voice/session/reply`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid, transcript, mode }),
        });

        if (sessionTokenRef.current !== token) return;

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `Server error ${resp.status}`);
        }

        const data = await resp.json();

        if (data.status === "ready") {
          setState("ready");
          // Small delay before redirecting so Redis (Upstash) has time to
          // persist the mark_ready write before the planner page opens its
          // SSE connection to /api/voice/session/{id}/plan.
          // Without this, the server may read a stale "collecting" status.
          await new Promise((resolve) => setTimeout(resolve, 600));
          if (sessionTokenRef.current !== token) return;
          onReady(sid, messagesRef.current);
          return;
        }

        // Follow-up question from the agent
        if (data.status === "follow_up" && data.question) {
          appendMessage(
            "assistant",
            data.question,
            data.question_audio_b64 ?? null,
            data.question_audio_format ?? null,
          );
          setState("follow_up");

          // Turn-taking: only start listening immediately if there is NO audio playback.
          // Otherwise, we wait for onAudioEnd to be triggered when the audio completes.
          if (autoListenEnabledRef.current) {
            if (!data.question_audio_b64) {
              await startListening();
            }
          }
        }
      } catch (e: unknown) {
        if (sessionTokenRef.current !== token) return;
        const msg = e instanceof Error ? e.message : "Server error";
        setError(msg);
        setState("error");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode, onReady, appendMessage],
  );

  const startListening = useCallback(async () => {
    const client = voiceClientRef.current;
    if (!client) return;
    if (client.currentStatus !== "idle") return;
    setState("listening");
    await client.start();
  }, []);

  // ── Public API ────────────────────────────────────────────────────────

  /** Tap mic — initialise session if needed, then start listening. */
  const startSession = useCallback(async () => {
    setError(null);
    autoListenEnabledRef.current = true;

    // If we already have a session and are in follow_up or listening, just start listening
    if (sessionIdRef.current && (state === "follow_up" || state === "listening")) {
      await startListening();
      return;
    }

    const token = Math.random().toString(36).slice(2, 10);
    sessionTokenRef.current = token;

    // In error/idle state: clear any stale session before re-initialising
    if (state === "error" || state === "idle" || !sessionIdRef.current) {
      if (autoListenTimerRef.current) {
        clearTimeout(autoListenTimerRef.current);
        autoListenTimerRef.current = null;
      }
      setMessages([]);
      setDraft("");
      setSessionId(null);
      sessionIdRef.current = null;
    }

    // Fresh session
    setState("greeting");
    try {
      const resp = await fetch(`${API_URL}/api/voice/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      if (sessionTokenRef.current !== token) return;

      if (!resp.ok) throw new Error(`Session start failed: HTTP ${resp.status}`);
      const data = await resp.json();

      const sid: string = data.session_id;
      setSessionId(sid);
      sessionIdRef.current = sid;

      // Show greeting as first assistant message
      appendMessage(
        "assistant",
        data.greeting_text,
        data.greeting_audio_b64 ?? null,
        data.greeting_audio_format ?? null,
      );

      // Turn-taking: only start listening immediately if there is NO greeting audio.
      // Otherwise, we wait for onAudioEnd to be triggered when the greeting audio completes.
      if (data.greeting_audio_b64) {
        setState("greeting");
      } else {
        setState("listening");
        await startListening();
      }
    } catch (e: unknown) {
      if (sessionTokenRef.current !== token) return;
      const msg = e instanceof Error ? e.message : "Failed to start session";
      // "Failed to fetch" means the backend URL is unreachable (backend not running
      // or wrong NEXT_PUBLIC_API_URL). Surface a clearer message.
      const isNetworkError =
        msg.toLowerCase().includes("failed to fetch") ||
        msg.toLowerCase().includes("networkerror") ||
        msg.toLowerCase().includes("load failed");
      if (isNetworkError) {
        setError(
          "Cannot reach the backend server. Make sure the backend is running at " +
            (API_URL || "http://localhost:8000") +
            " and try again."
        );
      } else {
        setError(`${msg}. Please try typing your request.`);
      }
      setState("error");
    }
  }, [state, mode, appendMessage, startListening]);

  /** Manual stop recording. */
  const stopRecording = useCallback(() => {
    autoListenEnabledRef.current = false;
    voiceClientRef.current?.stop();
    setIsRecording(false);
  }, []);

  /**
   * Reset the session back to idle — used when switching modes so the
   * previous session's state (e.g. "follow_up") doesn't auto-trigger
   * recording when the user comes back to this mode.
   */
  const reset = useCallback(() => {
    sessionTokenRef.current = null;
    autoListenEnabledRef.current = true;
    // Cancel any pending auto-listen timer
    if (autoListenTimerRef.current) {
      clearTimeout(autoListenTimerRef.current);
      autoListenTimerRef.current = null;
    }
    // Stop any active recording
    voiceClientRef.current?.stop();
    setIsRecording(false);
    // Clear all session state
    setState("idle");
    setMessages([]);
    setDraft("");
    setError(null);
    setSessionId(null);
    sessionIdRef.current = null;
  }, []);

  /** Transcription mode — user clicks Send. */
  const submitDraft = useCallback(async () => {
    // Block while the session is in a transitional state
    const busyStates: VoiceSessionState[] = ["agent_thinking", "greeting", "processing", "ready"];
    if (!draft.trim() || busyStates.includes(state)) return;
    const text = draft.trim();
    setDraft("");
    appendMessage("user", text, null);
    await submitToServer(text);
  }, [draft, state, appendMessage, submitToServer]);

  const onAudioEnd = useCallback(async () => {
    if (autoListenEnabledRef.current) {
      if (state === "greeting" || state === "follow_up") {
        setState("listening");
        await startListening();
      }
    }
  }, [state, startListening]);

  const initAudioContext = useCallback(() => {
    voiceClientRef.current?.initAudioContext();
  }, []);

  return {
    state,
    messages,
    draft,
    error,
    isRecording,
    sessionId,
    setDraft,
    startSession,
    stopRecording,
    submitDraft,
    reset,
    onAudioEnd,
    initAudioContext,
  };
}
