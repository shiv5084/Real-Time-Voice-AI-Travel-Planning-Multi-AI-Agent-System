"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import VoiceAudioPlayer from "@/components/VoiceAudioPlayer";
import { useRouter } from "next/navigation";
import { openSSE } from "@/lib/sse";
import { api } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────
type PlanningStatus = "idle" | "gathering_info" | "planning" | "done" | "error";

interface PlanStep {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface TripPlanResponse {
  trip_id: string;
  trace_id: string;
  pipeline_status: string;
  validation_status?: string;
  itinerary?: any;
  budget_breakdown?: any;
  follow_up_questions?: string[];
  errors?: Array<{ agent?: string; error?: string; message?: string }>;
  total_latency_ms?: number;
}

// ── Constants ─────────────────────────────────────────────────────────────
const PIPELINE_STEPS: PlanStep[] = [
  { id: "planner",     label: "Planning trip",          status: "pending" },
  { id: "flights",     label: "Searching flights",       status: "pending" },
  { id: "hotels",      label: "Finding hotels",          status: "pending" },
  { id: "attractions", label: "Discovering attractions", status: "pending" },
  { id: "transport",   label: "Calculating routes",      status: "pending" },
  { id: "budget",      label: "Optimising budget",       status: "pending" },
  { id: "composer",    label: "Composing itinerary",     status: "pending" },
  { id: "validator",   label: "Validating plan",         status: "pending" },
];

const AGENT_STEP_INDEX: Record<string, number> = {
  planner: 0, flights: 1, hotels: 2, attractions: 3,
  transport: 4, budget: 5, composer: 6, validator: 7,
};

const DATE_QUESTION =
  'When would you like to travel? Please provide your start date? (e.g. "June 10, 2026" or "10th June 2026").';
const BUDGET_QUESTION =
  'What is your total budget for this trip? (e.g. "$3000", "$2500 total for 2 people")';

function makeId() {
  return Math.random().toString(36).slice(2);
}

function calculateEndDate(startDateStr: string, numDays: number): string {
  if (!startDateStr) return "";
  const d = new Date(startDateStr);
  if (isNaN(d.getTime())) return "";
  d.setDate(d.getDate() + Math.max(0, numDays - 1));
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd}`;
}

// ── Detect travel info in text ────────────────────────────────────────────
function textHasCalendarDate(text: string): boolean {
  const t = text.toLowerCase();
  return (
    /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}/i.test(text) ||
    /\b\d{1,2}\s*(st|nd|rd|th)?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(text) ||
    /\b\d{4}-\d{2}-\d{2}\b/.test(text) ||
    /\b\d{1,2}[\/\-]\d{1,2}([\\/\-]\d{2,4})?\b/.test(text) ||
    /\bnext\s+(month|week|year|summer|winter|spring|fall|autumn)\b/i.test(t) ||
    /\bthis\s+(month|week|summer|winter|spring|fall|autumn)\b/i.test(t) ||
    /\bin\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b/i.test(t) ||
    /\b(early|mid|late|end\s+of)\s+(january|february|march|april|may|june|july|august|september|october|november|december)\b/i.test(t)
  );
}

function textHasBudget(text: string): boolean {
  if (/[$€£₹¥₩₽฿₫₱₲₵₿]\s*[\d,]+/.test(text)) return true;
  if (/[\d,]+\s*(k|K)?\s+(dollars?|euros?|pounds?|rupees?|bucks?|usd|eur|gbp|inr)\b/i.test(text)) return true;
  if (/\b(USD|EUR|GBP|INR|JPY|AUD|CAD)\s+[\d,]+/i.test(text)) return true;
  if (/\bbudget\s*[:=]?\s*[\d,]+/i.test(text)) return true;
  if (/[\d,]+\s*(k|K)?\s*budget\b/i.test(text)) return true;
  return false;
}

function detectRequiredInfo(texts: string[]): { has_dates: boolean; has_budget: boolean } {
  const combined = texts.join(" ");
  return {
    has_dates: texts.some(textHasCalendarDate) || textHasCalendarDate(combined),
    has_budget: texts.some(textHasBudget) || textHasBudget(combined),
  };
}

// ── Spinner component ─────────────────────────────────────────────────────
function Spinner({ size = 20, color = "#e03e52" }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      style={{ animation: "spin 1s linear infinite", flexShrink: 0 }}
    >
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="3" strokeOpacity="0.25" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

// Module-level cache to preserve search parameters across React Strict Mode double-mount
let cachedSessionId: string | null = null;
let cachedQ: string | null = null;

// ── Main Planner Page ─────────────────────────────────────────────────────
export default function PlannerPage() {
  const router = useRouter();

  const [messages, setMessages]             = useState<ChatMessage[]>([]);
  const [steps, setSteps]                   = useState<PlanStep[]>([]);
  const [planStatus, setPlanStatus]         = useState<PlanningStatus>("idle");
  const [error, setError]                   = useState<string | null>(null);
  const [tripId, setTripId]                 = useState<string | null>(null);
  const [itinerary, setItinerary]           = useState<any>(null);
  const [budgetBreakdown, setBudgetBreakdown] = useState<any>(null);
  const [currentAgentMsg, setCurrentAgentMsg] = useState<string>("");
  const [chatInput, setChatInput]           = useState("");
  const [voiceSummaryText, setVoiceSummaryText] = useState<string | null>(null);
  const [voiceSummaryAudioB64, setVoiceSummaryAudioB64] = useState<string | null>(null);
  const [voiceSummaryAudioFormat, setVoiceSummaryAudioFormat] = useState<string | null>(null);
  const [isVoice, setIsVoice] = useState(false);

  const voiceMicRef = useRef<HTMLDivElement | null>(null);
  const userTextsRef       = useRef<string[]>([]);
  const pendingQuestionRef = useRef<"dates" | "budget" | null>(null);
  const sseCleanupRef      = useRef<(() => void) | null>(null);
  const chatEndRef         = useRef<HTMLDivElement>(null);
  const inputRef           = useRef<HTMLInputElement>(null);

  // Scroll chat to bottom when messages change
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Step animation (text mode) ────────────────────────────────────────
  const animateSteps = useCallback(() => {
    setSteps(PIPELINE_STEPS.map((s) => ({ ...s })));
    let idx = 0;
    const timer = setInterval(() => {
      if (idx >= PIPELINE_STEPS.length) { clearInterval(timer); return; }
      setSteps((prev) =>
        prev.map((s, i) =>
          i < idx ? { ...s, status: "done" }
          : i === idx ? { ...s, status: "running" }
          : s
        )
      );
      idx++;
    }, 800);
    return timer;
  }, []);

  // ── Voice Session SSE path ────────────────────────────────────────────
  const runVoiceSessionPlan = useCallback((sessionId: string) => {
    sessionStorage.removeItem("last_planner_state");
    setPlanStatus("planning");
    setError(null);
    setSteps(PIPELINE_STEPS.map((s) => ({ ...s })));
    setCurrentAgentMsg("Analysing your travel request…");

    const cleanup = openSSE(`/api/voice/session/${sessionId}/plan`, {
      onOpen: () => {
        console.log("[VoicePlan] SSE stream opened");
      },
      onMessage: ({ event, data }) => {
        const payload = typeof data === "string" ? JSON.parse(data) : data as any;

        if (event === "agent_start") {
          const agentId: string = payload.agent ?? "";
          const idx = AGENT_STEP_INDEX[agentId] ?? -1;
          if (idx >= 0) {
            setSteps((prev) =>
              prev.map((s, i) =>
                i < idx  ? { ...s, status: "done" }
                : i === idx ? { ...s, status: "running" }
                : s
              )
            );
          }
          setCurrentAgentMsg(payload.message ?? `Running ${agentId}…`);
        }

        else if (event === "agent_done") {
          const agentId: string = payload.agent ?? "";
          const idx = AGENT_STEP_INDEX[agentId] ?? -1;
          if (idx >= 0) {
            setSteps((prev) =>
              prev.map((s, i) => (i === idx ? { ...s, status: "done" } : s))
            );
          }
          setCurrentAgentMsg("");
        }

        else if (event === "plan_complete") {
          setSteps(PIPELINE_STEPS.map((s) => ({ ...s, status: "done" })));
          setPlanStatus("done");
          setTripId(payload.trip_id ?? null);
          setItinerary(payload.itinerary ?? null);
          setBudgetBreakdown(payload.budget_breakdown ?? null);
          setCurrentAgentMsg("");

          setTimeout(() => {
            voiceMicRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
          }, 300);

          if (payload.errors?.length) {
            const hasRateLimit = payload.errors.some((e: any) =>
              (e.error ?? "").includes("429") || (e.error ?? "").includes("rate_limit")
            );
            if (hasRateLimit) {
              setError("Note: AI model rate limit hit — used fallback plan. Results may be less detailed.");
            }
          }
        }

        else if (event === "voice_summary") {
          setVoiceSummaryText(payload.text ?? null);
          setVoiceSummaryAudioB64(payload.audio_b64 ?? null);
          setVoiceSummaryAudioFormat(payload.audio_format ?? null);
        }

        else if (event === "error") {
          setError(payload.error ?? "An error occurred during planning.");
          setPlanStatus("error");
          setSteps((prev) =>
            prev.map((s) => (s.status === "running" ? { ...s, status: "error" } : s))
          );
          setCurrentAgentMsg("");
        }
      },
      onError: (err) => {
        console.error("[VoicePlan] SSE error:", err);
        const msg =
          err instanceof Error
            ? err.message
            : "Connection error — your plan may still be generating.";
        const isSessionError =
          msg.includes("400") ||
          msg.includes("404") ||
          msg.includes("not yet ready") ||
          msg.includes("not found");
        setError(
          isSessionError
            ? "Voice session expired — please try your request again."
            : msg
        );
        setPlanStatus("error");
        setCurrentAgentMsg("");
      },
    });

    sseCleanupRef.current = cleanup;
  }, []);

  // ── Text mode pipeline ────────────────────────────────────────────────
  const runPipeline = useCallback(async (augmentedRequest: string) => {
    setPlanStatus("planning");
    setError(null);
    setCurrentAgentMsg("Analysing your travel request…");
    const timer = animateSteps();

    try {
      const resp = await api.post<TripPlanResponse>("/api/trips/plan", {
        raw_request: augmentedRequest,
      });
      clearInterval(timer);
      setCurrentAgentMsg("");

      setTripId(resp.trip_id);
      setItinerary(resp.itinerary ?? null);
      setBudgetBreakdown(resp.budget_breakdown ?? null);

      if (resp.itinerary || resp.budget_breakdown) {
        setSteps(PIPELINE_STEPS.map((s) => ({ ...s, status: "done" })));
        setPlanStatus("done");
      } else if (resp.follow_up_questions?.length) {
        setPlanStatus("gathering_info");
        const nextQ = resp.follow_up_questions[0];
        pendingQuestionRef.current = nextQ.toLowerCase().includes("date") ? "dates" : "budget";
        setMessages((prev) => [
          ...prev,
          { id: makeId(), role: "assistant", content: nextQ, timestamp: new Date() },
        ]);
      } else {
        setSteps(PIPELINE_STEPS.map((s) => ({ ...s, status: "done" })));
        setPlanStatus("done");
      }

      if (resp.errors?.length) {
        const hasRateLimit = resp.errors.some((e) =>
          (e.error ?? "").includes("429") || (e.error ?? "").includes("rate_limit")
        );
        if (hasRateLimit) setError("Note: AI rate limit — used fallback plan. Results may vary.");
      }
    } catch (err: unknown) {
      clearInterval(timer);
      setSteps((prev) => prev.map((s) => (s.status === "running" ? { ...s, status: "error" } : s)));
      setError(err instanceof Error ? err.message : "Planning failed");
      setPlanStatus("error");
      setCurrentAgentMsg("");
    }
  }, [animateSteps]);

  const askNextQuestion = useCallback((info: { has_dates: boolean; has_budget: boolean }) => {
    if (!info.has_dates) {
      pendingQuestionRef.current = "dates";
      setMessages((prev) => [...prev, { id: makeId(), role: "assistant", content: DATE_QUESTION, timestamp: new Date() }]);
      return;
    }
    if (!info.has_budget) {
      pendingQuestionRef.current = "budget";
      setMessages((prev) => [...prev, { id: makeId(), role: "assistant", content: BUDGET_QUESTION, timestamp: new Date() }]);
      return;
    }
    pendingQuestionRef.current = null;
    runPipeline(userTextsRef.current.join("\n\n"));
  }, [runPipeline]);

  const startPlanning = useCallback((text: string) => {
    if (planStatus === "planning") return;
    sessionStorage.removeItem("last_planner_state");
    userTextsRef.current = [text];
    pendingQuestionRef.current = null;
    setError(null);
    setTripId(null);
    setItinerary(null);
    setBudgetBreakdown(null);
    setVoiceSummaryText(null);
    setSteps([]);
    setMessages([{ id: makeId(), role: "user", content: text, timestamp: new Date() }]);

    const info = detectRequiredInfo([text]);
    if (!info.has_dates || !info.has_budget) {
      setPlanStatus("gathering_info");
      askNextQuestion(info);
    } else {
      runPipeline(text);
    }
  }, [planStatus, askNextQuestion, runPipeline]);

  // ── URL param detection ───────────────────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const qParam = params.get("q");
    const sessionParam = params.get("session_id");

    if (qParam || sessionParam) {
      // Clear previous cached state if starting a new request/session
      sessionStorage.removeItem("last_planner_state");
    } else {
      // Only restore previous state if there are no new parameters in the URL
      const savedStateStr = sessionStorage.getItem("last_planner_state");
      if (savedStateStr) {
        try {
          const savedState = JSON.parse(savedStateStr);
          if (savedState.planStatus === "done") {
            setPlanStatus("done");
            setTripId(savedState.tripId);
            setItinerary(savedState.itinerary);
            setBudgetBreakdown(savedState.budgetBreakdown);
            setVoiceSummaryText(savedState.voiceSummaryText);
            setVoiceSummaryAudioB64(savedState.voiceSummaryAudioB64);
            setVoiceSummaryAudioFormat(savedState.voiceSummaryAudioFormat);
            setIsVoice(savedState.isVoice);
            setSteps(savedState.steps);
            
            // Restore messages — JSON.parse turns Date objects into ISO strings,
            // so we must re-hydrate them back to Date instances
            if (savedState.messages) {
              setMessages(savedState.messages.map((m: any) => ({
                ...m,
                timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
              })));
            }
            
            if (savedState.isVoice) {
              setTimeout(() => {
                voiceMicRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
              }, 500);
            }
            return;
          }
        } catch (e) {
          console.error("Failed to restore planner state from sessionStorage", e);
        }
      }
    }

    let q = qParam;
    let sessionId = sessionParam;

    if (sessionId) {
      cachedSessionId = sessionId;
    } else {
      sessionId = cachedSessionId;
    }

    if (q) {
      cachedQ = q;
    } else {
      q = cachedQ;
    }

    if (params.get("session_id") || params.get("q")) {
      window.history.replaceState({}, "", window.location.pathname);
    }

    if (sessionId) {
      setIsVoice(true);
      let savedMsgs: ChatMessage[] = [];
      try {
        const stored = localStorage.getItem(`voice_session_messages_${sessionId}`);
        if (stored) {
          const parsed = JSON.parse(stored);
          if (Array.isArray(parsed)) {
            savedMsgs = parsed.map((m: any) => ({
              id: m.id || makeId(),
              role: m.role,
              content: m.content,
              timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
            }));
          }
        }
      } catch (e) {
        console.error("Failed to load voice messages from localStorage", e);
      }

      if (savedMsgs.length > 0) {
        setMessages(savedMsgs);
      } else {
        setMessages([{
          id: makeId(),
          role: "assistant",
          content: "🎙️ Planning trip…",
          timestamp: new Date(),
        }]);
      }
      runVoiceSessionPlan(sessionId);
    } else if (q) {
      startPlanning(q);
    } else {
      // No params — redirect back to home
      router.replace("/");
    }

    return () => {
      sseCleanupRef.current?.();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Voice Summary Audio Playback ──────────────────────────────────────
  // Audio is handled entirely by <VoiceAudioPlayer audioB64={voiceSummaryAudioB64} />
  // which provides: autoplay, browser-blocked prompt, waveform animation, and replay.

  // Save state to sessionStorage when itinerary or voice summary changes
  useEffect(() => {
    if (planStatus === "done" && (itinerary || budgetBreakdown)) {
      const stateObj = {
        planStatus,
        tripId,
        itinerary,
        budgetBreakdown,
        voiceSummaryText,
        voiceSummaryAudioB64,
        voiceSummaryAudioFormat,
        isVoice,
        steps: steps.map(s => ({ ...s, status: s.status === "running" ? "done" : s.status })),
        messages, // Persist chat messages across reloads
      };
      sessionStorage.setItem("last_planner_state", JSON.stringify(stateObj));
    }
  }, [planStatus, tripId, itinerary, budgetBreakdown, voiceSummaryText, voiceSummaryAudioB64, voiceSummaryAudioFormat, isVoice, steps, messages]);

  // ── Chat send ─────────────────────────────────────────────────────────
  const handleChatSend = useCallback(() => {
    const text = chatInput.trim();
    if (!text) return;
    setChatInput("");

    if (planStatus === "done") {
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: "user", content: text, timestamp: new Date() },
        { id: makeId(), role: "assistant", content: "Your itinerary is ready above. To plan a new trip, go back to the home page.", timestamp: new Date() },
      ]);
      return;
    }

    userTextsRef.current = [...userTextsRef.current, text];
    setMessages((prev) => [...prev, { id: makeId(), role: "user", content: text, timestamp: new Date() }]);

    const info = detectRequiredInfo(userTextsRef.current);
    if (pendingQuestionRef.current === "dates" && textHasCalendarDate(text)) {
      askNextQuestion(info);
    } else if (pendingQuestionRef.current === "budget" && textHasBudget(text)) {
      askNextQuestion(info);
    } else {
      askNextQuestion(info);
    }
  }, [chatInput, planStatus, askNextQuestion]);

  // ── Derived ───────────────────────────────────────────────────────────
  const isPlanning = planStatus === "planning";
  const isDone     = planStatus === "done";
  const isGathering = planStatus === "gathering_info";
  const hasSteps   = steps.length > 0;

  const doneCount = steps.filter((s) => s.status === "done").length;
  const runningStep = steps.find((s) => s.status === "running");

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--bg-base)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Main content ── */}
      <div
        style={{
          flex: 1,
          maxWidth: 760,
          margin: "0 auto",
          width: "100%",
          padding: "32px 16px 40px",
          display: "flex",
          flexDirection: "column",
          gap: 20,
        }}
      >
        {/* ── Center Voice Assistant Panel (only for voice sessions) ── */}
        {isVoice && (
          <div
            ref={voiceMicRef}
            style={{
              background: "var(--bg-surface)",
              border: "1px solid rgba(224, 62, 82, 0.25)",
              borderRadius: 16,
              padding: "24px",
              boxShadow: "0 8px 32px rgba(224, 62, 82, 0.08), 0 4px 24px rgba(0,0,0,0.35)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 20,
              width: "100%",
            }}
            className="animate-fade-in"
          >
            {/* Panel Header */}
            <div style={{ width: "100%", borderBottom: "1px solid var(--border)", paddingBottom: 12, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>🎙️</span>
              <span style={{ fontSize: 13, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-primary)" }}>
                Voice Assistant Panel
              </span>
            </div>

            {/* Mic Interface */}
            <div className="flex flex-col items-center justify-center" style={{ textAlign: "center" }}>
              <VoiceAudioPlayer
                audioB64={voiceSummaryAudioB64}
                audioMimeType={voiceSummaryAudioFormat ?? undefined}
                autoPlay={true}
                className="mt-4"
                waitingLabel={!isDone ? "Planning trip…" : "Tap Mic to Replay Summary"}
              />
            </div>

            {/* Voice Summary Text inside the Panel */}
            {isDone && voiceSummaryText && (
              <div
                style={{
                  background: "rgba(224,62,82,0.04)",
                  borderLeft: "3px solid var(--accent)",
                  borderRadius: "4px 12px 12px 4px",
                  padding: "14px 18px",
                  width: "100%",
                  textAlign: "left",
                }}
                className="animate-fade-in"
              >
                <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--accent)", marginBottom: 6, marginTop: 0 }}>
                  Voice Summary Transcript
                </p>
                <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: 0, fontStyle: "italic", lineHeight: 1.5 }}>
                  "{voiceSummaryText}"
                </p>
              </div>
            )}
          </div>
        )}

        {/* ── Planning progress card ── */}
        {(isPlanning || isGathering || hasSteps) && (
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: 16,
              padding: "20px 24px",
              boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
            }}
            className="animate-fade-in"
          >
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <span style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)" }}>
                {isDone ? "Your trip is ready! 🎉" : "Planning your trip."}
              </span>
              {isPlanning && <Spinner size={20} color="#e03e52" />}
              {isDone && (
                <span style={{ fontSize: 18 }}>✓</span>
              )}
            </div>

            {/* Steps list */}
            {hasSteps && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {steps.map((step) => (
                  <div key={step.id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    {/* Status icon */}
                    {step.status === "done" && (
                      <span style={{ color: "#22c55e", fontSize: 14, fontWeight: 700, width: 18, textAlign: "center" }}>✓</span>
                    )}
                    {step.status === "running" && (
                      <span style={{ width: 18, display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <Spinner size={14} color="#e03e52" />
                      </span>
                    )}
                    {step.status === "pending" && (
                      <span style={{ color: "var(--text-disabled)", fontSize: 14, width: 18, textAlign: "center" }}>○</span>
                    )}
                    {step.status === "error" && (
                      <span style={{ color: "var(--error)", fontSize: 14, width: 18, textAlign: "center" }}>✕</span>
                    )}

                    {/* Label */}
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: step.status === "running" ? 600 : 400,
                        color:
                          step.status === "done"    ? "#22c55e"
                          : step.status === "running" ? "#e03e52"
                          : step.status === "error"  ? "var(--error)"
                          : "var(--text-muted)",
                        transition: "color 0.3s ease",
                      }}
                    >
                      {step.label}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Gathering info step */}
            {isGathering && !hasSteps && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Spinner size={14} color="#e03e52" />
                <span style={{ fontSize: 13, color: "#e03e52", fontWeight: 600 }}>Planning trip</span>
              </div>
            )}
          </div>
        )}

        {/* ── Error alert ── */}
        {error && (
          <div
            style={{
              background: isDone ? "rgba(245,158,11,0.08)" : "rgba(239,68,68,0.08)",
              border: `1px solid ${isDone ? "rgba(245,158,11,0.3)" : "rgba(239,68,68,0.3)"}`,
              borderRadius: 12,
              padding: "12px 16px",
            }}
            role="alert"
          >
            <p style={{ fontSize: 13, color: isDone ? "var(--warning)" : "var(--error)", margin: 0 }}>
              {isDone ? "💡" : "⚠"} {error}
            </p>
            {error.toLowerCase().includes("session expired") && (
              <button
                onClick={() => router.push("/")}
                style={{
                  marginTop: 10,
                  padding: "6px 14px",
                  background: "var(--accent)",
                  color: "#fff",
                  border: "none",
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Go Back Home
              </button>
            )}
          </div>
        )}

        {/* ── Itinerary ready banner ── */}
        {isDone && tripId && (
          <div
            style={{
              background: "rgba(34,197,94,0.08)",
              border: "1px solid rgba(34,197,94,0.3)",
              borderRadius: 12,
              padding: "14px 18px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
            className="animate-fade-in"
          >
            <p style={{ fontSize: 14, fontWeight: 600, color: "#22c55e", margin: 0 }}>
              ✓ Your itinerary is ready!
            </p>
            <button
              onClick={() => router.push(`/itinerary/${tripId}`)}
              style={{
                padding: "8px 18px",
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              View Itinerary →
            </button>
          </div>
        )}



        {/* ── Full itinerary ── */}
        {isDone && (itinerary || budgetBreakdown) && (
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border)",
              borderRadius: 16,
              padding: "20px 24px",
              boxShadow: "0 4px 24px rgba(0,0,0,0.4)",
            }}
            className="animate-fade-in"
          >
            <h2 style={{ fontSize: 15, fontWeight: 700, color: "var(--text-primary)", marginBottom: 20 }}>
              Your Complete Travel Plan
            </h2>

            {/* Destination & dates */}
            {itinerary && (() => {
              const startDateVal = itinerary.startDate || (itinerary.days && itinerary.days[0]?.date);
              let endDateVal = itinerary.endDate || (itinerary.days && itinerary.days[itinerary.days.length - 1]?.date);
              if (startDateVal && (!endDateVal || endDateVal === startDateVal) && itinerary.days && itinerary.days.length > 1) {
                endDateVal = calculateEndDate(startDateVal, itinerary.days.length);
              }
              const dateRangeStr = startDateVal && endDateVal ? `${startDateVal} - ${endDateVal}` : startDateVal || endDateVal || "";

              return (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 40, marginBottom: 20 }}>
                  <div>
                    <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>Destination</p>
                    <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                      📍 {itinerary.destination ? String(itinerary.destination) : "TBD"}
                    </p>
                  </div>
                  <div>
                    <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>start date - end date</p>
                    <p style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                      🗓 {dateRangeStr || "TBD"}
                    </p>
                  </div>
                </div>
              );
            })()}

            {/* Day-by-day */}
            {itinerary?.days && Array.isArray(itinerary.days) && itinerary.days.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>
                  Day-by-Day Itinerary
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {(itinerary.days as any[]).map((day: any, idx: number) => (
                    <div
                      key={idx}
                      style={{
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        borderRadius: 12,
                        padding: "14px 16px",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                        <h4 style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                          Day {day.day ?? idx + 1}{day.location ? ` — ${day.location}` : ""}
                        </h4>
                        {day.date && <span style={{ fontSize: 11, color: "var(--text-muted)" }}>{day.date}</span>}
                      </div>
                      {day.activities && Array.isArray(day.activities) && (
                        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                          {(day.activities as any[]).map((act: any, ai: number) => (
                            <li key={ai} style={{ display: "flex", alignItems: "flex-start", gap: 8, fontSize: 12 }}>
                              <span style={{ fontFamily: "monospace", color: "var(--accent)", flexShrink: 0, width: 52 }}>{act.start_time ?? ""}</span>
                              <span style={{ flex: 1, color: "var(--text-secondary)" }}>
                                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{act.name}</span>
                                {act.description ? ` — ${act.description}` : ""}
                              </span>
                              {act.cost_usd != null && act.cost_usd > 0 && (
                                <span style={{ flexShrink: 0, fontWeight: 600, color: "var(--text-muted)" }}>${act.cost_usd}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                      {day.notes && <p style={{ marginTop: 8, fontSize: 11, fontStyle: "italic", color: "var(--text-muted)" }}>💡 {day.notes}</p>}
                      {day.total_cost_usd != null && (
                        <p style={{ marginTop: 8, fontSize: 11, fontWeight: 700, textAlign: "right", color: "var(--text-muted)" }}>
                          Day total: ${day.total_cost_usd}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Budget breakdown */}
            {budgetBreakdown && (
              <div>
                <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 12 }}>Budget Breakdown</p>
                {Array.isArray((budgetBreakdown as any).categories) && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                    {((budgetBreakdown as any).categories as any[]).map((cat: any, i: number) => (
                      <div
                        key={i}
                        style={{
                          background: "var(--bg-elevated)",
                          border: "1px solid var(--border)",
                          borderRadius: 10,
                          padding: "12px 14px",
                        }}
                      >
                        <p style={{ fontSize: 10, textTransform: "capitalize", color: "var(--text-muted)", marginBottom: 4 }}>{cat.category}</p>
                        <p style={{ fontSize: 14, fontWeight: 700, color: "var(--text-primary)" }}>${Number(cat.amount ?? 0).toFixed(0)}</p>
                      </div>
                    ))}
                  </div>
                )}
                {(budgetBreakdown as any).total_estimated_cost != null && (() => {
                  const comp = (budgetBreakdown as any).compliance || "within_budget";
                  const limit = (budgetBreakdown as any).total_budget;
                  const recommendations = (budgetBreakdown as any).recommendations || [];
                  
                  let bgColor = "rgba(34, 197, 94, 0.08)";
                  let borderColor = "rgba(34, 197, 94, 0.3)";
                  let textColor = "#22c55e";
                  let statusText = "Within Budget";

                  if (comp === "over_budget") {
                    bgColor = "rgba(239, 68, 68, 0.08)";
                    borderColor = "rgba(239, 68, 68, 0.3)";
                    textColor = "#ef4444";
                    statusText = "Over Budget";
                  } else if (comp === "warning") {
                    bgColor = "rgba(245, 158, 11, 0.08)";
                    borderColor = "rgba(245, 158, 11, 0.3)";
                    textColor = "#f59e0b";
                    statusText = "Near Budget Limit";
                  }

                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                      <div
                        style={{
                          background: bgColor,
                          border: `1px solid ${borderColor}`,
                          borderRadius: 10,
                          padding: "14px 16px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                        }}
                      >
                        <div>
                          <p style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", margin: 0 }}>
                            Total Estimated Cost
                          </p>
                          {limit > 0 && (
                            <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "2px 0 0" }}>
                              Budget Limit: ${Number(limit).toFixed(0)} ({statusText})
                            </p>
                          )}
                        </div>
                        <p style={{ fontSize: 20, fontWeight: 800, color: textColor, margin: 0 }}>
                          ${Number((budgetBreakdown as any).total_estimated_cost).toFixed(0)}
                        </p>
                      </div>

                      {/* Suggested Adjustments */}
                      {comp === "over_budget" && recommendations && recommendations.length > 0 && (
                        <div
                          style={{
                            background: "rgba(239, 68, 68, 0.04)",
                            border: "1px dashed rgba(239, 68, 68, 0.3)",
                            borderRadius: 10,
                            padding: "14px 16px",
                            marginTop: 8,
                          }}
                        >
                          <p style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "#ef4444", marginBottom: 8, marginTop: 0 }}>
                            💡 Suggested Budget Adjustments
                          </p>
                          <ul style={{ paddingLeft: 16, margin: 0, fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 6 }}>
                            {recommendations.map((rec: string, rIdx: number) => (
                              <li key={rIdx}>{rec}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        )}

        {/* ── Chat conversation ── */}
        {messages.length > 0 && (
          <div>
            {/* Section header */}
            <h2
              style={{
                fontSize: 13,
                fontWeight: 700,
                color: "var(--text-muted)",
                marginBottom: 12,
                textTransform: "uppercase",
                letterSpacing: "0.08em",
              }}
            >
              {isDone ? "Your plan is ready — ask anything" : isPlanning ? "Planning trip…" : "Gathering details…"}
            </h2>

            {/* Messages */}
            <div
              style={{
                background: "var(--bg-surface)",
                border: "1px solid var(--border)",
                borderRadius: 16,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  maxHeight: 420,
                  overflowY: "auto",
                  padding: "16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    style={{
                      display: "flex",
                      justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                      alignItems: "flex-start",
                      gap: 10,
                      flexDirection: msg.role === "user" ? "row-reverse" : "row",
                    }}
                    className="animate-fade-in"
                  >
                    {/* Avatar Circle */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}>
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: "50%",
                          background: msg.role === "user" ? "var(--accent)" : "var(--bg-elevated)",
                          border: msg.role === "user" ? "none" : "1px solid var(--border)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 13,
                          fontWeight: 700,
                          color: msg.role === "user" ? "#fff" : "var(--accent)",
                          boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                        }}
                      >
                        {msg.role === "user" ? "U" : "A"}
                      </div>
                      {msg.role === "assistant" && isVoice && (
                        <span style={{ fontSize: 12 }} title="Voice Mode">🎙️</span>
                      )}
                    </div>

                    {/* Chat Bubble */}
                    <div
                      style={{
                        maxWidth: "70%",
                        padding: "10px 14px",
                        borderRadius: msg.role === "user" ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
                        background: msg.role === "user" ? "var(--accent)" : "var(--bg-elevated)",
                        border: msg.role === "user" ? "none" : "1px solid var(--border)",
                        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                      }}
                    >
                      <p style={{ fontSize: 14, color: msg.role === "user" ? "#fff" : "var(--text-primary)", margin: 0, lineHeight: 1.5 }}>
                        {msg.content}
                      </p>
                      <p style={{ fontSize: 10, color: msg.role === "user" ? "rgba(255,255,255,0.6)" : "var(--text-muted)", marginTop: 4, marginBottom: 0, textAlign: "right" }}>
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}

                {/* Typing indicator during planning */}
                {isPlanning && currentAgentMsg && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-start",
                      alignItems: "flex-start",
                      gap: 10,
                      flexDirection: "row",
                    }}
                  >
                    {/* Avatar Circle */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4, flexShrink: 0 }}>
                      <div
                        style={{
                          width: 32,
                          height: 32,
                          borderRadius: "50%",
                          background: "var(--bg-elevated)",
                          border: "1px solid var(--border)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 13,
                          fontWeight: 700,
                          color: "var(--accent)",
                          boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                        }}
                      >
                        A
                      </div>
                      {isVoice && (
                        <span style={{ fontSize: 12 }} title="Voice Mode">🎙️</span>
                      )}
                    </div>

                    <div
                      style={{
                        padding: "10px 14px",
                        borderRadius: "16px 16px 16px 4px",
                        background: "var(--bg-elevated)",
                        border: "1px solid var(--border)",
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <Spinner size={12} color="#e03e52" />
                      <span style={{ fontSize: 13, color: "var(--text-muted)", fontStyle: "italic" }}>{currentAgentMsg}</span>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              {/* Chat input */}
              {(isGathering || isDone) && (
                <div
                  style={{
                    borderTop: "1px solid var(--border)",
                    padding: "12px 16px",
                    display: "flex",
                    gap: 10,
                  }}
                >
                  <input
                    ref={inputRef}
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleChatSend(); } }}
                    placeholder={isDone ? "Ask a follow-up question…" : "Type your answer…"}
                    style={{
                      flex: 1,
                      background: "var(--bg-elevated)",
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      padding: "9px 14px",
                      fontSize: 14,
                      color: "var(--text-primary)",
                      outline: "none",
                    }}
                  />
                  <button
                    onClick={handleChatSend}
                    disabled={!chatInput.trim()}
                    style={{
                      padding: "9px 18px",
                      background: chatInput.trim() ? "var(--accent)" : "var(--bg-elevated)",
                      color: chatInput.trim() ? "#fff" : "var(--text-muted)",
                      border: "none",
                      borderRadius: 10,
                      fontSize: 14,
                      fontWeight: 600,
                      cursor: chatInput.trim() ? "pointer" : "not-allowed",
                      transition: "all 0.2s ease",
                    }}
                  >
                    Send
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── New trip button (after done) ── */}
        {isDone && (
          <div style={{ textAlign: "center" }} className="animate-fade-in">
            <button
              onClick={() => router.push("/")}
              style={{
                padding: "10px 24px",
                background: "transparent",
                color: "var(--text-muted)",
                border: "1px solid var(--border)",
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.2s",
              }}
              onMouseOver={(e) => {
                (e.target as HTMLButtonElement).style.color = "var(--text-primary)";
                (e.target as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.2)";
              }}
              onMouseOut={(e) => {
                (e.target as HTMLButtonElement).style.color = "var(--text-muted)";
                (e.target as HTMLButtonElement).style.borderColor = "var(--border)";
              }}
            >
              ← Plan Another Trip
            </button>
          </div>
        )}

        {/* ── Empty state: no session, no query ── */}
        {planStatus === "idle" && messages.length === 0 && (
          <div style={{ textAlign: "center", padding: "60px 20px" }}>
            <p style={{ fontSize: 16, color: "var(--text-muted)", marginBottom: 20 }}>
              No trip found. Start planning from the home page.
            </p>
            <button
              onClick={() => router.push("/")}
              style={{
                padding: "12px 28px",
                background: "var(--accent)",
                color: "#fff",
                border: "none",
                borderRadius: 10,
                fontSize: 14,
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              Go to Home →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
