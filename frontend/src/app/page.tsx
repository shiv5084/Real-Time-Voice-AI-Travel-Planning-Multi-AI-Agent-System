"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import VoiceTranscriptBox from "@/components/VoiceTranscriptBox";
import { useVoiceSession } from "@/hooks/useVoiceSession";

type VoiceMode = "realtime" | "transcription";

export default function LandingPage() {
  const router = useRouter();

  // ── Testing / Mock Voice Mode ─────────────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("mock_voice") === "true") {
      console.log("[MOCK VOICE] Initialising testing mocks...");
      
      // Mock getUserMedia to return a fake stream (avoids AudioContext recursion/permissions)
      if (typeof navigator !== "undefined" && navigator.mediaDevices) {
        navigator.mediaDevices.getUserMedia = async function() {
          console.log('[MOCK USERMEDIA] Called getUserMedia');
          const track = {
            kind: 'audio',
            enabled: true,
            id: 'mock-track-id',
            label: 'Mock Audio Track',
            readyState: 'live',
            stop: () => {},
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => true,
          };
          const stream = {
            getAudioTracks: () => [track],
            getVideoTracks: () => [],
            getTracks: () => [track],
            addTrack: () => {},
            removeTrack: () => {},
            clone: () => stream,
            active: true,
            id: 'mock-stream-id',
            addEventListener: () => {},
            removeEventListener: () => {},
            dispatchEvent: () => true,
          };
          return stream as unknown as MediaStream;
        };
      }

      // Mock MediaRecorder to handle the fake stream
      if (typeof window !== "undefined") {
        window.MediaRecorder = class MockMediaRecorder extends EventTarget {
          stream: any;
          state: string = "inactive";
          ondataavailable: any = null;
          onstop: any = null;
          constructor(stream: any) {
            super();
            this.stream = stream;
          }
          start(timeslice?: number) {
            this.state = "recording";
            setTimeout(() => {
              if (this.state === "recording") {
                const event = new MessageEvent("dataavailable", {
                  data: new Blob(["mock-audio-data"], { type: "audio/webm" }),
                }) as any;
                this.ondataavailable?.(event);
              }
            }, 200);
          }
          stop() {
            this.state = "inactive";
            setTimeout(() => {
              this.onstop?.();
            }, 50);
          }
          static isTypeSupported(type: string) {
            return true;
          }
        } as any;
      }

      // Mock transcribe endpoint
      const originalFetch = window.fetch;
      let transcribeCount = 0;
      window.fetch = async function(url, options) {
        const urlStr = typeof url === 'string'
          ? url
          : (url instanceof URL ? url.toString() : (url as Request).url || '');
        if (urlStr.includes('/api/voice/transcribe')) {
          transcribeCount++;
          console.log('[MOCK STT] Intercepted transcribe call, count =', transcribeCount);
          let transcript = "";
          if (transcribeCount === 1) {
            transcript = "Plan a 5-day trip to Paris for a couple with a $3000 budget, love museums and romantic dining, hate crowds";
          } else {
            transcript = "We want to travel starting June 15, 2026.";
          }
          return new Response(JSON.stringify({
            trace_id: "mock-trace-" + Math.random(),
            transcript: transcript,
            language: "en",
            confidence: 0.99,
            editable: true,
            requires_confirmation: true,
            fallback_to_text: false
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        }
        return originalFetch.apply(this, arguments as any);
      };
    }
  }, []);

  // ── Text mode state ───────────────────────────────────────────────────
  const [query, setQuery] = useState("");
  const [textError, setTextError] = useState<string | null>(null);

  // ── Voice mode state ──────────────────────────────────────────────────
  const [voiceMode, setVoiceMode] = useState<VoiceMode>("realtime");
  const [voiceActive, setVoiceActive] = useState(false);
  const voiceActiveRef = useRef(false);

  const changeVoiceActive = (val: boolean) => {
    voiceActiveRef.current = val;
    setVoiceActive(val);
  };

  // ── Voice session (realtime) ──────────────────────────────────────────
  const realtimeSession = useVoiceSession({
    mode: "realtime",
    onReady: (sid, msgs) => {
      if (typeof window !== "undefined") {
        const sanitizedMsgs = msgs.map(({ audioB64, audioFormat, ...rest }) => rest);
        try {
          localStorage.setItem(`voice_session_messages_${sid}`, JSON.stringify(sanitizedMsgs));
        } catch (err) {
          console.warn("[VOICE] Failed to save messages to localStorage", err);
        }
      }
      router.push(`/planner?session_id=${sid}&mode=realtime`);
    },
  });

  const transcriptionSession = useVoiceSession({
    mode: "transcription",
    onReady: (sid, msgs) => {
      if (typeof window !== "undefined") {
        const sanitizedMsgs = msgs.map(({ audioB64, audioFormat, ...rest }) => rest);
        try {
          localStorage.setItem(`voice_session_messages_${sid}`, JSON.stringify(sanitizedMsgs));
        } catch (err) {
          console.warn("[VOICE] Failed to save messages to localStorage", err);
        }
      }
      router.push(`/planner?session_id=${sid}&mode=transcription`);
    },
  });

  const activeSession = voiceMode === "realtime" ? realtimeSession : transcriptionSession;

  // ── Text mode submit ──────────────────────────────────────────────────
  const handleTextSubmit = () => {
    const q = query.trim();
    if (!q) {
      setTextError("Please describe your trip or tap the microphone to speak.");
      return;
    }
    router.push(`/planner?q=${encodeURIComponent(q)}`);
  };

  const handleSuggestionClick = (text: string) => {
    setQuery(text);
    changeVoiceActive(false);
  };

  // ── Mic tap ───────────────────────────────────────────────────────────
  const handleMicToggle = async (e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();

    // Unlock Web Audio API context synchronously on user gesture (click event) for mobile support.
    activeSession.initAudioContext?.();

    const isSessionInactive = activeSession.state === "idle" || activeSession.state === "error";

    if (!voiceActiveRef.current || isSessionInactive) {
      // ── Activate / Reactivate session ────────────────────────────────────
      const scrollY = window.scrollY;
      const html = document.documentElement;
      html.style.position = "fixed";
      html.style.top = `-${scrollY}px`;
      html.style.width = "100%";
      html.style.overflowY = "scroll";

      changeVoiceActive(true);

      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          html.style.position = "";
          html.style.top = "";
          html.style.width = "";
          html.style.overflowY = "";
          window.scrollTo({ top: scrollY, behavior: "instant" });
        });
      });

      await activeSession.startSession();

    } else {
      // ── Deactivate / Stop session (remain in voice mode UI) ───────────────
      if (voiceMode === "realtime") {
        // In real-time mode, clicking again stops/deactivates the session,
        // but remains in voice mode (does not set voiceActive to false).
        activeSession.reset();
      } else {
        // In transcription (edit) mode:
        if (activeSession.isRecording) {
          // If recording, stop recording (keeps session alive so user can edit/send transcript)
          activeSession.stopRecording();
        } else if (activeSession.state === "follow_up") {
          // If not recording, tap to record/speak another turn
          await activeSession.startSession();
        } else {
          // Otherwise, reset the session but stay in voice mode
          activeSession.reset();
        }
      }
    }
  };

  // ── Derived display ───────────────────────────────────────────────────
  const micLabel = (() => {
    const s = activeSession.state;
    if (s === "greeting")       return "Connecting…";
    if (s === "listening")      return "Listening…";
    if (s === "processing")     return "Transcribing…";
    if (s === "agent_thinking") return "AI thinking…";
    if (s === "follow_up")      return voiceMode === "realtime" ? "Tap mic to answer" : "Edit & Send below";
    if (s === "ready")          return "Redirecting…";
    if (s === "error")          return "Try again";
    return voiceMode === "realtime" ? "Tap Microphone to Speak" : "Tap Microphone to Record";
  })();

  const micBusy =
    activeSession.state === "greeting" ||
    activeSession.state === "processing" ||
    activeSession.state === "agent_thinking" ||
    activeSession.state === "ready";

  const isRecording = activeSession.isRecording;

  return (
    <div className="flex flex-col min-h-screen">
      {/* ── Hero Section ────────────────────────────────────────────── */}
      <section
        className="relative flex flex-col items-center justify-center px-6 pt-20 pb-16 text-center overflow-hidden"
        aria-labelledby="hero-heading"
        style={{
          backgroundImage: "url('/travel-background.png')",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundRepeat: "no-repeat",
        }}
      >
        {/* Dark overlay */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "linear-gradient(to bottom, rgba(10,10,15,0.4) 0%, rgba(10,10,15,0) 25%, rgba(10,10,15,0) 75%, rgba(10,10,15,0.85) 100%)",
          }}
        />
        {/* Radial glow removed to prevent reddish hue */}

        {/* Content */}
        <div className="relative z-10 w-full flex flex-col items-center">
          <p
            className="mb-3 text-[13px] font-bold uppercase tracking-[0.2em]"
            style={{
              color: "var(--accent)",
              textShadow: "0 1px 4px rgba(0, 0, 0, 0.5)",
            }}
          >
            AI-Powered Travel Planning
          </p>

          <h1
            id="hero-heading"
            className="mb-4 max-w-4xl text-4xl font-extrabold leading-tight sm:text-6xl tracking-tight"
            style={{
              color: "var(--text-primary)",
              textShadow: "0 2px 10px rgba(0, 0, 0, 0.7), 0 4px 20px rgba(0, 0, 0, 0.4)",
            }}
          >
            Plan your next dream trip with your voice.
          </h1>

          <p
            className="mb-10 max-w-2xl text-[15px] sm:text-[16px] font-medium leading-relaxed"
            style={{
              color: "#ffffff",
              textShadow: "0 1px 4px rgba(0, 0, 0, 0.7), 0 2px 8px rgba(0, 0, 0, 0.5)",
            }}
          >
            Speak your travel request. Our multi-agent AI searches flights, hotels,
            attractions, and local transport — then crafts a personalised itinerary
            in seconds.
          </p>

          {/* ── Mic + Mode Toggle row ─── */}
          <div className="flex flex-col items-center justify-center mb-6">
            <div className="flex items-center gap-4 mb-4">
              {/* Mic button */}
              <button
                type="button"
                onClick={(e) => handleMicToggle(e)}
                onMouseDown={(e) => e.preventDefault()}
                disabled={micBusy}
                aria-label={isRecording ? "Stop recording" : "Start voice recording"}
                aria-pressed={isRecording}
                className={`relative flex h-20 w-20 items-center justify-center rounded-2xl text-4xl shadow-xl transition-all duration-300 hover:scale-105 active:scale-95 border disabled:opacity-60 disabled:cursor-not-allowed ${
                  isRecording
                    ? "bg-green-600 border-green-500 animate-pulse"
                    : micBusy
                    ? "bg-amber-600 border-amber-500 animate-pulse"
                    : "bg-[#8B0000] border-[#8B0000] hover:bg-[#A52A2A] hover:shadow-[0_0_25px_rgba(139,0,0,0.4)]"
                }`}
              >
                {isRecording && (
                  <span className="absolute inset-0 rounded-2xl border-2 border-green-400 animate-ping opacity-75" />
                )}
                {micBusy && !isRecording ? "⏳" : isRecording ? "⏹" : "🎙️"}
              </button>

              {/* Mode toggle */}
              <button
                type="button"
                onClick={() => {
                  realtimeSession.reset();
                  transcriptionSession.reset();
                  setVoiceMode((m) => (m === "realtime" ? "transcription" : "realtime"));
                  changeVoiceActive(false);
                }}
                className={`relative flex items-center h-20 px-2 rounded-2xl border-2 transition-all duration-300 ${
                  voiceMode === "realtime"
                    ? "bg-[#e03e52]/10 border-[#e03e52]"
                    : "bg-gray-800 border-gray-700"
                }`}
                aria-label={`Switch to ${voiceMode === "realtime" ? "edit" : "real-time"} mode`}
              >
                <div
                  className={`absolute h-16 w-16 rounded-xl transition-all duration-300 flex items-center justify-center text-2xl ${
                    voiceMode === "realtime"
                      ? "left-1 bg-[#e03e52] text-white"
                      : "right-1 bg-gray-600 text-gray-300"
                  }`}
                >
                  {voiceMode === "realtime" ? "⚡" : "✏️"}
                </div>
                <div className="flex w-40 justify-between px-4">
                  <span
                    className={`text-xs font-bold uppercase tracking-wider transition-colors ${
                      voiceMode === "realtime" ? "text-[#e03e52]" : "text-gray-500"
                    }`}
                  >
                    Real-Time
                  </span>
                  <span
                    className={`text-xs font-bold uppercase tracking-wider transition-colors ${
                      voiceMode === "transcription" ? "text-[#e03e52]" : "text-gray-500"
                    }`}
                  >
                    Edit Mode
                  </span>
                </div>
              </button>
            </div>

            <span className="text-xs text-gray-500 font-bold tracking-wider uppercase">
              {micLabel}
            </span>

            {(activeSession.error || textError) && (
              <span
                className="text-xs text-red-500 mt-2 font-medium max-w-sm text-center"
                role="alert"
              >
                {activeSession.error || textError}
              </span>
            )}
          </div>

          {/* ── Voice transcript box (shown when voice is active) ─── */}
          {voiceActive && (
            <div
              className="w-full max-w-2xl px-4 mb-6"
              style={{ overflowAnchor: "none" } as React.CSSProperties}
            >
              <VoiceTranscriptBox
                messages={activeSession.messages}
                mode={voiceMode}
                draft={activeSession.draft}
                onDraftChange={activeSession.setDraft}
                onSubmit={activeSession.submitDraft}
                onAudioEnd={activeSession.onAudioEnd}
                agentThinking={activeSession.state === "agent_thinking"}
                disabled={micBusy}
              />
            </div>
          )}

          {/* ── Text input (shown when voice is NOT active) ─────── */}
          {!voiceActive && (
            <>
              <div className="w-full max-w-2xl px-4 mb-4">
                <div className="relative rounded-2xl border border-gray-800 bg-[#111117]/80 backdrop-blur-md p-3 shadow-lg focus-within:border-[#e03e52]/60 focus-within:shadow-[0_0_15px_rgba(224,62,82,0.15)] transition-all">
                  <textarea
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      if (textError) setTextError(null);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleTextSubmit();
                      }
                    }}
                    placeholder="Describe your trip (e.g. 5 days in Paris for 2 people, $3000 budget)"
                    rows={3}
                    className="w-full bg-transparent text-gray-200 placeholder-gray-500 focus:outline-none resize-none text-[15px]"
                    aria-label="Trip request"
                  />
                </div>
              </div>

              <div className="w-full max-w-2xl px-4">
                <button
                  type="button"
                  onClick={handleTextSubmit}
                  className="btn-dark-red w-full rounded-2xl px-8 py-4 text-[16px] tracking-wide"
                  aria-label="Generate my travel plan"
                >
                  <span className="btn-shimmer" aria-hidden="true" />
                  <span style={{ position: "relative", zIndex: 2 }}>
                    Generate My Travel Plan
                  </span>
                </button>
              </div>
            </>
          )}

          <div className="flex items-center gap-2 mt-8 mb-16">
            <span className="h-1.5 w-1.5 rounded-full bg-gray-600" />
            <span className="h-1.5 w-1.5 rounded-full bg-[#e03e52]" />
            <span className="h-1.5 w-1.5 rounded-full bg-gray-600" />
          </div>
        </div>
      </section>

      {/* ── Suggestion prompts ──────────────────────────────────────── */}
      <section className="w-full max-w-5xl mx-auto px-6 pb-20">
        <h2 className="text-center text-xs font-bold tracking-[0.25em] text-gray-500 uppercase mb-8">
          TRY ASKING THESE REQUESTS
        </h2>
        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              icon: "🏰",
              text: "Plan a 5-day trip to Paris for a couple with a $3000 budget, love museums and romantic dining, hate crowds",
            },
            {
              icon: "🎒",
              text: "Budget friendly solo backpacking trip to Southeast Asia for a week",
            },
            {
              icon: "🏢",
              text: "Luxury weekend getaway to New York City",
            },
          ].map((item, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => handleSuggestionClick(item.text)}
              className="flex flex-col items-start text-left p-6 rounded-2xl border border-gray-800 bg-[#111117]/60 hover:bg-[#111117] hover:border-[#e03e52]/40 hover:shadow-[0_0_15px_rgba(224,62,82,0.08)] transition-all duration-300 group focus:outline-none"
            >
              <span className="text-3xl mb-4 group-hover:scale-110 transition-transform">
                {item.icon}
              </span>
              <p className="text-sm font-medium text-gray-400 group-hover:text-gray-200 transition-colors leading-relaxed">
                {item.text}
              </p>
            </button>
          ))}
        </div>
      </section>

      {/* ── Featured Destinations ───────────────────────────────────── */}
      <section className="w-full max-w-5xl mx-auto px-6 pb-28">
        <div className="mb-10 text-left">
          <h2 className="text-3xl font-extrabold text-white mb-2">Featured Destinations</h2>
          <p className="text-sm text-gray-500 font-semibold uppercase tracking-wider">
            Hand-picked by our AI travel experts.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          {[
            {
              name: "Dubai",
              tag: "Trending",
              badgeColor: "rgba(224,62,82,0.15)",
              textColor: "#e03e52",
              image:
                "https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=600&auto=format&fit=crop&q=80",
              query:
                "A luxury 4-day trip to Dubai with desert safari and skyline touring",
            },
            {
              name: "Paris",
              tag: "Romantic",
              badgeColor: "rgba(235,104,76,0.15)",
              textColor: "#eb684c",
              image:
                "https://images.unsplash.com/photo-1502602898657-3e91760cbb34?w=600&auto=format&fit=crop&q=80",
              query:
                "A romantic 5-day escape to Paris exploring art, gourmet cafes, and gardens",
            },
            {
              name: "Tokyo",
              tag: "Vibrant",
              badgeColor: "rgba(56,189,248,0.15)",
              textColor: "#38bdf8",
              image:
                "https://images.unsplash.com/photo-1503899036084-c55cdd92da26?w=600&auto=format&fit=crop&q=80",
              query:
                "An active 7-day adventure in Tokyo exploring pop culture, neon streets, and sushi",
            },
          ].map((dest, idx) => (
            <div
              key={idx}
              onClick={() => handleSuggestionClick(dest.query)}
              className="relative h-96 rounded-2xl overflow-hidden cursor-pointer group shadow-lg"
            >
              <img
                src={dest.image}
                alt={dest.name}
                className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-110"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/10" />
              <div className="absolute top-4 left-4">
                <span
                  className="badge rounded-full px-3 py-1 font-bold tracking-wide text-xs"
                  style={{
                    backgroundColor: dest.badgeColor,
                    color: dest.textColor,
                    border: `1px solid ${dest.textColor}30`,
                  }}
                >
                  {dest.tag}
                </span>
              </div>
              <div className="absolute bottom-6 left-6">
                <span className="text-2xl font-bold text-white transition-colors group-hover:text-[#e03e52]">
                  {dest.name}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ──────────────────────────────────────────────────── */}
      <footer className="w-full bg-[#0a0a0f] border-t border-gray-900 px-6 py-12 text-sm text-gray-500 mt-auto">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div className="max-w-md">
            <span className="text-lg font-bold text-white block mb-1">PlanMyTrip AI</span>
            <p className="text-gray-600 font-medium">
              Designing the future of human exploration through high-performance intelligence.
            </p>
          </div>
          <div className="flex flex-wrap gap-8 font-semibold">
            <a href="#" className="hover:text-white transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-white transition-colors">Terms of Service</a>
            <a href="#" className="hover:text-white transition-colors">Support</a>
            <a href="#" className="hover:text-white transition-colors">Careers</a>
            <span>© 2026 PlanMyTrip AI. All rights reserved.</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
