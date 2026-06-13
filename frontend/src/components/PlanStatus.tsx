"use client";

import { useEffect, useState } from "react";

export interface PlanStep {
  id: string;
  label: string;
  status: "pending" | "running" | "done" | "error";
  detail?: string;
}

interface PlanStatusProps {
  steps: PlanStep[];
  /** Overall status of the planning run */
  overallStatus?: "idle" | "planning" | "awaiting_followup" | "done" | "error";
  className?: string;
}

const STEP_ICONS: Record<PlanStep["status"], string> = {
  pending: "○",
  running: "◉",
  done:    "✓",
  error:   "✕",
};

const STEP_COLORS: Record<PlanStep["status"], string> = {
  pending: "var(--text-muted)",
  running: "var(--accent)",
  done:    "var(--success)",
  error:   "var(--error)",
};

// Default pipeline steps shown before any SSE data arrives
const DEFAULT_STEPS: PlanStep[] = [
  { id: "planner",    label: "Planning trip",           status: "pending" },
  { id: "flights",    label: "Searching flights",        status: "pending" },
  { id: "hotels",     label: "Finding hotels",           status: "pending" },
  { id: "attractions",label: "Discovering attractions",  status: "pending" },
  { id: "transport",  label: "Calculating routes",       status: "pending" },
  { id: "budget",     label: "Optimising budget",        status: "pending" },
  { id: "composer",   label: "Composing itinerary",      status: "pending" },
  { id: "validator",  label: "Validating plan",          status: "pending" },
];

export default function PlanStatus({
  steps = DEFAULT_STEPS,
  overallStatus = "idle",
  className = "",
}: PlanStatusProps) {
  const [dots, setDots] = useState(".");

  // Animated dots for running steps
  useEffect(() => {
    if (overallStatus !== "planning") return;
    const id = setInterval(() => {
      setDots((d) => (d.length >= 3 ? "." : d + "."));
    }, 500);
    return () => clearInterval(id);
  }, [overallStatus]);

  if (overallStatus === "idle") return null;

  return (
    <section
      className={`card p-4 ${className}`}
      aria-label="Trip planning status"
      aria-live="polite"
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {overallStatus === "planning" && `Planning your trip${dots}`}
          {overallStatus === "awaiting_followup" && "Waiting for your response"}
          {overallStatus === "done"     && "Plan ready ✓"}
          {overallStatus === "error"    && "Planning failed"}
        </h3>

        {overallStatus === "planning" && (
          <svg
            className="animate-spin h-4 w-4"
            style={{ color: "var(--accent)" }}
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        )}
      </div>

      <ol className="flex flex-col gap-1.5" aria-label="Pipeline steps">
        {steps.map((step) => (
          <li
            key={step.id}
            className="flex items-center gap-3 text-sm"
            aria-current={step.status === "running" ? "step" : undefined}
          >
            <span
              className="w-4 shrink-0 text-center font-mono text-xs"
              style={{ color: STEP_COLORS[step.status] }}
              aria-hidden="true"
            >
              {step.status === "running" ? (
                <svg
                  className="animate-spin h-3 w-3"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                STEP_ICONS[step.status]
              )}
            </span>

            <div className="flex flex-1 items-center justify-between gap-2">
              <span style={{ color: STEP_COLORS[step.status] }}>{step.label}</span>
              {step.detail && (
                <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                  {step.detail}
                </span>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
