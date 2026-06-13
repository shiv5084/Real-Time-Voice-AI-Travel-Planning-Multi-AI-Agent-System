"use client";

import { useState } from "react";
import { getSupabaseClient } from "@/lib/auth";

// ── Types ────────────────────────────────────────────────────────────────

interface PreferenceState {
  accommodation_type?: string;
  transport_preference?: string;
  airline_preference?: string;
  budget_style?: string;
  food?: string;
  travel_style?: string;
}

type PrefKey = keyof PreferenceState;

interface Option {
  /** Exact value sent to the backend — must match TravelPreferences field values */
  value: string;
  label: string;
  icon: string;
}

interface Category {
  /** Exact field name matching the backend TravelPreferences Pydantic model */
  name: PrefKey;
  label: string;
  options: Option[];
}

interface Step {
  title: string;
  subtitle: string;
  categories: [Category, Category]; // always exactly 2 per step
}

// ── Step definitions ─────────────────────────────────────────────────────
// Field names and values are kept in sync with:
//   backend/app/routers/profile.py  → TravelPreferences
//   backend/app/memory/mem0_client.py → PREFERENCE_KEYS

const STEPS: Step[] = [
  {
    title: "Let's personalise your travel experience",
    subtitle: "Step 1 of 3",
    categories: [
      {
        name: "accommodation_type",
        label: "Accommodation Style",
        options: [
          { value: "hotel",   label: "Hotel",         icon: "🏨" },
          { value: "hostel",  label: "Hostel",         icon: "🏠" },
          { value: "airbnb",  label: "Airbnb",         icon: "🏡" },
          { value: "luxury",  label: "Luxury Resort",  icon: "🏰" },
        ],
      },
      {
        name: "transport_preference",
        label: "Transport",
        options: [
          { value: "public transit", label: "Public Transit",  icon: "🚇" },
          { value: "rental car",     label: "Rental Car",      icon: "🚗" },
          { value: "walking",        label: "Walking",          icon: "🚶" },
          { value: "taxi",           label: "Taxi/Rideshare",  icon: "🚕" },
        ],
      },
    ],
  },
  {
    title: "Fine-tune your travel preferences",
    subtitle: "Step 2 of 3",
    categories: [
      {
        name: "airline_preference",
        label: "Airline Preference",
        options: [
          { value: "Singapore Airlines", label: "Singapore Airlines", icon: "✈️" },
          { value: "Emirates",           label: "Emirates",           icon: "🛫" },
          { value: "Delta",              label: "Delta",              icon: "🌐" },
          { value: "British Airways",    label: "British Airways",    icon: "🇬🇧" },
        ],
      },
      {
        name: "budget_style",
        label: "Budget Style",
        options: [
          { value: "budget",     label: "Budget",     icon: "💰" },
          { value: "mid-range",  label: "Mid-Range",  icon: "💵" },
          { value: "luxury",     label: "Luxury",     icon: "💎" },
          { value: "backpacker", label: "Backpacker", icon: "🎒" },
        ],
      },
    ],
  },
  {
    title: "Almost there! Last preferences",
    subtitle: "Step 3 of 3",
    categories: [
      {
        name: "food",
        label: "Food Preference",
        options: [
          { value: "Italian",  label: "Italian",  icon: "🍝" },
          { value: "Japanese", label: "Japanese", icon: "🍣" },
          { value: "Mexican",  label: "Mexican",  icon: "🌮" },
          { value: "Indian",   label: "Indian",   icon: "🍛" },
        ],
      },
      {
        name: "travel_style",
        label: "Travel Style",
        options: [
          { value: "backpacker",  label: "Backpacker",  icon: "🎒" },
          { value: "cultural",    label: "Cultural",    icon: "🏛️" },
          { value: "adventure",   label: "Adventure",   icon: "🏔️" },
          { value: "relaxation",  label: "Relaxation",  icon: "🏖️" },
        ],
      },
    ],
  },
];

// ── Component ────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [preferences, setPreferences] = useState<PreferenceState>({});
  const [loading, setLoading] = useState(false);
  const [celebrating, setCelebrating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const step = STEPS[currentStep];
  const progress = ((currentStep + 1) / STEPS.length) * 100;

  // ── Handlers ────────────────────────────────────────────────────────

  const handleSelect = (categoryName: PrefKey, value: string) => {
    setPreferences((prev) => ({ ...prev, [categoryName]: value }));
    setError(null);
  };

  const validateStep = (): boolean => {
    const missing = step.categories
      .filter((c) => !preferences[c.name])
      .map((c) => c.label);
    if (missing.length > 0) {
      setError(`Please select an option for: ${missing.join(" and ")}`);
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (!validateStep()) return;
    setError(null);
    if (currentStep < STEPS.length - 1) {
      setCurrentStep((s) => s + 1);
    } else {
      handleSubmit();
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1);
      setError(null);
    }
  };

  const handleSkip = () => {
    setError(null);
    if (currentStep < STEPS.length - 1) {
      setCurrentStep((s) => s + 1);
    } else {
      handleSubmit();
    }
  };

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);
    try {
      const supabase = getSupabaseClient();
      const { data: { user }, error: userError } = await supabase.auth.getUser();
      if (userError || !user) throw new Error("User not authenticated. Please sign in again.");

      const { data: { session } } = await supabase.auth.getSession();
      if (!session?.access_token) throw new Error("No active session. Please sign in again.");

      const response = await fetch(
        `/api/profile/preferences?user_id=${user.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${session.access_token}`,
          },
          body: JSON.stringify(preferences),
        }
      );

      if (!response.ok) {
        let detail = "Failed to save preferences";
        try {
          const body = await response.json();
          detail = body?.detail ?? body?.message ?? detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }

      // ── Celebration: show overlay first, then fire confetti independently ──
      setCelebrating(true);
      setLoading(false);

      const DURATION_MS = 3000;

      // ── Confetti is isolated in its own try-catch so any failure
      //    (dynamic import error, CSP block, etc.) never prevents navigation ──
      try {
        // Dynamic import keeps canvas-confetti out of the SSR bundle entirely
        const { default: confetti } = await import("canvas-confetti");

        // Initial big burst from both sides
        const burst = (origin: { x: number; y: number }) =>
          confetti({
            particleCount: 80,
            spread: 70,
            origin,
            colors: ["#e03e52", "#ff5c75", "#ffffff", "#ffd700", "#22c55e"],
            zIndex: 9999,
          });

        burst({ x: 0.2, y: 0.6 });
        burst({ x: 0.8, y: 0.6 });

        // Sustained shower — fires every 60 ms for 3 seconds using setInterval
        const intervalId = setInterval(() => {
          confetti({
            particleCount: 6,
            angle: 60,
            spread: 55,
            origin: { x: 0 },
            colors: ["#e03e52", "#ff5c75", "#ffd700"],
            zIndex: 9999,
          });
          confetti({
            particleCount: 6,
            angle: 120,
            spread: 55,
            origin: { x: 1 },
            colors: ["#e03e52", "#ff5c75", "#22c55e"],
            zIndex: 9999,
          });
        }, 60);

        // Stop the shower when the celebration window ends
        setTimeout(() => clearInterval(intervalId), DURATION_MS);
      } catch {
        // Confetti failed silently — navigation will still proceed on schedule
      }

      // ── Navigation is set unconditionally, independent of confetti success ──
      // Use window.location.href (hard navigate) instead of router.push() because
      // the component tree has been fully swapped by setCelebrating(true) and
      // Next.js App Router soft-navigation can silently no-op in that state.
      setTimeout(() => {
        window.location.href = "/";
      }, DURATION_MS);

    } catch (err: unknown) {
      // Reset overlay state so the error message is actually visible to the user
      setCelebrating(false);
      setError(err instanceof Error ? err.message : "Failed to save preferences");
      setLoading(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────

  // Full-screen celebration overlay shown for the 3-second confetti window
  if (celebrating) {
    return (
      <div
        className="fixed inset-0 flex flex-col items-center justify-center text-center px-6"
        style={{ background: "var(--bg-base, #0a0a0f)", zIndex: 9998 }}
      >
        <div className="animate-bounce mb-6 text-7xl">🎉</div>
        <h1
          className="text-4xl font-extrabold mb-3"
          style={{ color: "var(--text-primary)" }}
        >
          You're all set!
        </h1>
        <p className="text-lg max-w-md" style={{ color: "var(--text-muted)" }}>
          Your travel preferences have been saved. Let's start planning your next adventure.
        </p>
        <p className="text-sm mt-4" style={{ color: "var(--accent)" }}>
          Taking you to your home page…
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-4xl">

        {/* ── Progress bar ── */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold" style={{ color: "var(--accent)" }}>
              {step.subtitle}
            </span>
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              {Math.round(progress)}% complete
            </span>
          </div>
          {/* Step dots */}
          <div className="flex items-center gap-2 mb-3">
            {STEPS.map((_, i) => (
              <div
                key={i}
                className="h-1.5 flex-1 rounded-full transition-all duration-500"
                style={{
                  background:
                    i < currentStep
                      ? "#22c55e"
                      : i === currentStep
                      ? "linear-gradient(90deg, #e03e52, #ff5c75)"
                      : "rgba(255,255,255,0.1)",
                }}
              />
            ))}
          </div>
          <div className="h-1 rounded-full bg-gray-800 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 ease-out"
              style={{
                width: `${progress}%`,
                background: "linear-gradient(90deg, #e03e52, #ff5c75)",
              }}
            />
          </div>
        </div>

        {/* ── Title ── */}
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-extrabold mb-2" style={{ color: "var(--text-primary)" }}>
            {step.title}
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Select <strong>one option</strong> from each category below
          </p>
        </div>

        {/* ── Two category columns ── */}
        <div className="grid gap-8 md:grid-cols-2 mb-10">
          {step.categories.map((category) => {
            const selected = preferences[category.name];
            return (
              <div key={category.name}>
                {/* Category heading + selection indicator */}
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
                    {category.label}
                  </h2>
                  {selected ? (
                    <span
                      className="text-xs font-semibold rounded-full px-2.5 py-0.5 flex items-center gap-1"
                      style={{ background: "rgba(34,197,94,0.12)", color: "#22c55e" }}
                    >
                      <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      Selected
                    </span>
                  ) : (
                    <span
                      className="text-xs rounded-full px-2.5 py-0.5"
                      style={{ background: "rgba(224,62,82,0.1)", color: "#e03e52" }}
                    >
                      Required
                    </span>
                  )}
                </div>

                {/* 2×2 option card grid */}
                <div className="grid grid-cols-2 gap-3">
                  {category.options.map((option) => {
                    const isSelected = selected === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => handleSelect(category.name, option.value)}
                        aria-pressed={isSelected}
                        className="relative p-4 rounded-xl border-2 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#e03e52]"
                        style={{
                          borderColor: isSelected ? "#e03e52" : "rgba(255,255,255,0.08)",
                          background: isSelected
                            ? "rgba(224,62,82,0.10)"
                            : "rgba(255,255,255,0.03)",
                          boxShadow: isSelected
                            ? "0 0 20px rgba(224,62,82,0.25)"
                            : "none",
                        }}
                      >
                        <div className="flex flex-col items-center gap-2">
                          <span className="text-3xl leading-none">{option.icon}</span>
                          <span
                            className="text-sm font-medium text-center leading-tight"
                            style={{ color: isSelected ? "#e03e52" : "#d1d5db" }}
                          >
                            {option.label}
                          </span>
                        </div>

                        {/* Checkmark badge */}
                        {isSelected && (
                          <div
                            className="absolute top-2 right-2 w-5 h-5 rounded-full flex items-center justify-center"
                            style={{ background: "#e03e52" }}
                          >
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                            </svg>
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* ── Error message ── */}
        {error && (
          <div
            className="mb-6 p-4 rounded-xl text-center"
            style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.3)",
            }}
          >
            <p className="text-sm font-medium" style={{ color: "var(--error)" }}>{error}</p>
          </div>
        )}

        {/* ── Navigation ── */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleBack}
            disabled={currentStep === 0 || loading}
            className="btn btn-ghost flex-1"
            style={{ opacity: currentStep === 0 ? 0.4 : 1 }}
          >
            ← Back
          </button>

          <button
            type="button"
            onClick={handleSkip}
            disabled={loading}
            className="btn btn-ghost flex-shrink-0 px-5 text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            Skip step
          </button>

          <button
            type="button"
            onClick={handleNext}
            disabled={loading}
            className="btn btn-primary flex-1"
            style={{ background: "linear-gradient(135deg, #e03e52, #ff5c75)" }}
          >
            {loading
              ? "Saving…"
              : currentStep === STEPS.length - 1
              ? "Complete Setup ✓"
              : "Next →"}
          </button>
        </div>

        {/* ── Summary of selections so far ── */}
        {Object.values(preferences).some(Boolean) && (
          <div className="mt-8 p-4 rounded-xl" style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
            <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-muted)" }}>
              Your selections so far
            </p>
            <div className="flex flex-wrap gap-2">
              {STEPS.flatMap((s) => s.categories).map((cat) => {
                const val = preferences[cat.name];
                if (!val) return null;
                const opt = cat.options.find((o) => o.value === val);
                return (
                  <span
                    key={cat.name}
                    className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium"
                    style={{ background: "rgba(224,62,82,0.12)", color: "var(--text-primary)" }}
                  >
                    {opt?.icon} {opt?.label}
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
