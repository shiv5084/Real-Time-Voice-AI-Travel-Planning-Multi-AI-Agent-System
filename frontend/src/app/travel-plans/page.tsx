"use client";

import { useEffect, useRef, useState } from "react";
import { getSupabaseClient } from "@/lib/auth";

interface PreferenceState {
  accommodation_type?: string;
  transport_preference?: string;
  airline_preference?: string;
  budget_style?: string;
  food?: string;
  travel_style?: string;
  // backend also stores these — preserved in merge but not shown in UI
  crowd_tolerance?: string;
  activity_level?: string;
  dietary_restrictions?: string;
}

const PREFERENCE_CATEGORIES = [
  {
    key: "accommodation_type",
    label: "Accommodation Style",
    icon: "🏨",
    options: ["hotel", "hostel", "airbnb", "luxury"],
    displayLabels: ["Hotel", "Hostel", "Airbnb", "Luxury Resort"],
    optionIcons: ["🏨", "🏠", "🏡", "🏰"],
  },
  {
    key: "transport_preference",
    label: "Transport",
    icon: "🚗",
    options: ["public transit", "rental car", "walking", "taxi"],
    displayLabels: ["Public Transit", "Rental Car", "Walking", "Taxi/Rideshare"],
    optionIcons: ["🚇", "🚗", "🚶", "🚕"],
  },
  {
    key: "airline_preference",
    label: "Airline Preference",
    icon: "✈️",
    options: ["Singapore Airlines", "Emirates", "Delta", "British Airways"],
    displayLabels: ["Singapore Airlines", "Emirates", "Delta", "British Airways"],
    optionIcons: ["✈️", "🛫", "🌐", "🇬🇧"],
  },
  {
    key: "budget_style",
    label: "Budget Style",
    icon: "💰",
    options: ["budget", "mid-range", "luxury", "backpacker"],
    displayLabels: ["Budget", "Mid-Range", "Luxury", "Backpacker"],
    optionIcons: ["💰", "💵", "💎", "🎒"],
  },
  {
    key: "food",
    label: "Food Preference",
    icon: "🍽️",
    options: ["Italian", "Japanese", "Mexican", "Indian"],
    displayLabels: ["Italian", "Japanese", "Mexican", "Indian"],
    optionIcons: ["🍝", "🍣", "🌮", "🍛"],
  },
  {
    key: "travel_style",
    label: "Travel Style",
    icon: "🧳",
    options: ["backpacker", "cultural", "adventure", "relaxation"],
    displayLabels: ["Backpacker", "Cultural", "Adventure", "Relaxation"],
    optionIcons: ["🎒", "🏛️", "🏔️", "🏖️"],
  },
];

function usernameFromEmail(email: string): string {
  const local = email.split("@")[0] ?? email;
  return local
    .replace(/[._-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

// ── Custom dropdown — renders emoji + text reliably in all browsers ──────

interface DropdownOption {
  value: string;
  icon: string;
  label: string;
}

interface CustomDropdownProps {
  id: string;
  value: string;
  options: DropdownOption[];
  isDirty: boolean;
  onChange: (value: string) => void;
  ariaLabel: string;
}

function CustomDropdown({ id, value, options, isDirty, onChange, ariaLabel }: CustomDropdownProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    if (open) document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open]);

  const selected = options.find((o) => o.value === value);

  const triggerBg   = isDirty && value ? "rgba(224,62,82,0.08)" : "rgba(255,255,255,0.05)";
  const triggerBorder = isDirty && value ? "1px solid rgba(224,62,82,0.45)" : "1px solid rgba(255,255,255,0.1)";

  return (
    <div ref={containerRef} className="relative" id={id}>
      {/* Trigger button */}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-2 rounded-xl px-4 py-2.5 text-sm font-medium cursor-pointer transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#e03e52]/50"
        style={{
          background: triggerBg,
          border: triggerBorder,
          color: value ? "var(--text-primary)" : "var(--text-muted)",
        }}
      >
        <span className="flex items-center gap-2 min-w-0">
          {selected ? (
            <>
              <span className="text-base leading-none shrink-0">{selected.icon}</span>
              <span className="truncate">{selected.label}</span>
            </>
          ) : (
            <span className="truncate" style={{ color: "var(--text-muted)" }}>— no preference —</span>
          )}
        </span>
        <svg
          className="w-4 h-4 shrink-0 transition-transform duration-150"
          style={{
            color: "var(--text-muted)",
            transform: open ? "rotate(180deg)" : "rotate(0deg)",
          }}
          fill="none" viewBox="0 0 24 24" stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Options list */}
      {open && (
        <ul
          role="listbox"
          aria-label={ariaLabel}
          className="absolute z-40 mt-1 w-full rounded-xl overflow-hidden shadow-2xl py-1"
          style={{
            background: "#1a1a24",
            border: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          {/* Clear option */}
          <li
            role="option"
            aria-selected={!value}
            onClick={() => { onChange(""); setOpen(false); }}
            className="flex items-center gap-2 px-4 py-2.5 text-sm cursor-pointer transition-colors"
            style={{
              color: !value ? "#e03e52" : "var(--text-muted)",
              background: !value ? "rgba(224,62,82,0.08)" : "transparent",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.05)")}
            onMouseLeave={(e) => (e.currentTarget.style.background = !value ? "rgba(224,62,82,0.08)" : "transparent")}
          >
            <span className="text-base leading-none">—</span>
            <span>no preference</span>
          </li>

          {options.map((opt) => {
            const isSelected = value === opt.value;
            return (
              <li
                key={opt.value}
                role="option"
                aria-selected={isSelected}
                onClick={() => { onChange(opt.value); setOpen(false); }}
                className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm cursor-pointer transition-colors"
                style={{
                  color: isSelected ? "#e03e52" : "var(--text-primary)",
                  background: isSelected ? "rgba(224,62,82,0.08)" : "transparent",
                }}
                onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = "rgba(255,255,255,0.05)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = isSelected ? "rgba(224,62,82,0.08)" : "transparent"; }}
              >
                <span className="flex items-center gap-2 min-w-0">
                  <span className="text-base leading-none shrink-0">{opt.icon}</span>
                  <span className="truncate">{opt.label}</span>
                </span>
                {isSelected && (
                  <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" style={{ color: "#e03e52" }}>
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────

export default function TravelPlansPage() {
  const [preferences, setPreferences] = useState<PreferenceState>({});
  const [savedPreferences, setSavedPreferences] = useState<PreferenceState>({});
  const [displayName, setDisplayName] = useState<string>("");
  const [userEmail, setUserEmail] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => { loadProfile(); }, []);

  useEffect(() => {
    setHasChanges(JSON.stringify(preferences) !== JSON.stringify(savedPreferences));
  }, [preferences, savedPreferences]);

  const loadProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const supabase = getSupabaseClient();
      const { data: { user }, error: userError } = await supabase.auth.getUser();
      if (userError || !user) throw new Error("User not authenticated");

      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token ?? "";

      const metaName =
        user.user_metadata?.display_name ||
        user.user_metadata?.full_name ||
        user.user_metadata?.name || "";
      setDisplayName(metaName || usernameFromEmail(user.email ?? ""));
      setUserEmail(user.email ?? "");

      const res = await fetch(`/api/profile?user_id=${user.id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (res.ok) {
        const data = await res.json();
        const prefs = data.preferences ?? {};
        setPreferences(prefs);
        setSavedPreferences(prefs);
      } else if (res.status === 400) {
        setPreferences({});
        setSavedPreferences({});
      } else {
        throw new Error(`Failed to load preferences (${res.status})`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load preferences");
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const supabase = getSupabaseClient();
      const { data: { user }, error: userError } = await supabase.auth.getUser();
      if (userError || !user) throw new Error("User not authenticated");

      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token ?? "";

      const res = await fetch(`/api/profile/preferences?user_id=${user.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(preferences),
      });

      if (!res.ok) {
        let detail = "Failed to save preferences";
        try { const b = await res.json(); detail = b?.detail ?? b?.message ?? detail; } catch { /* ignore */ }
        throw new Error(detail);
      }

      setSavedPreferences({ ...preferences });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 4000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save preferences");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => { setPreferences({ ...savedPreferences }); setError(null); };

  const handleChange = (key: string, value: string) => {
    setPreferences((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const savedCount = Object.values(savedPreferences).filter(Boolean).length;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#e03e52] mx-auto mb-4" />
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>Loading your preferences…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="mb-8">
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text-primary)" }}>
              My Travel Plans
            </h1>
            {displayName && (
              <p className="text-base font-medium" style={{ color: "var(--accent)" }}>
                👋 Welcome, {displayName}
              </p>
            )}
            {userEmail && (
              <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>{userEmail}</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            {hasChanges && (
              <button type="button" onClick={handleReset} disabled={saving} className="btn btn-ghost text-sm">
                Discard Changes
              </button>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="btn btn-primary"
              style={{
                background: hasChanges ? "linear-gradient(135deg, #e03e52, #ff5c75)" : undefined,
                opacity: hasChanges ? 1 : 0.45,
              }}
            >
              {saving ? "Saving…" : "Save Preferences"}
            </button>
          </div>
        </div>

        <p className="text-sm mt-3" style={{ color: "var(--text-muted)" }}>
          {savedCount > 0
            ? `${savedCount} preference${savedCount === 1 ? "" : "s"} saved · use the dropdowns to update any preference`
            : "Set your travel preferences below to personalise trip recommendations."}
        </p>
      </div>

      {/* ── Notifications ──────────────────────────────────────────────── */}
      {success && (
        <div className="mb-6 p-4 rounded-lg flex items-center gap-3"
          style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)" }}>
          <span className="text-xl">✅</span>
          <p className="text-sm font-medium" style={{ color: "var(--success)" }}>
            Preferences saved successfully!
          </p>
        </div>
      )}
      {error && (
        <div className="mb-6 p-4 rounded-lg flex items-center gap-3"
          style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)" }}>
          <span className="text-xl">⚠️</span>
          <p className="text-sm" style={{ color: "var(--error)" }}>{error}</p>
        </div>
      )}

      {/* ── Preference Grid ─────────────────────────────────────────────── */}
      <div className="grid gap-5 md:grid-cols-2">
        {PREFERENCE_CATEGORIES.map((category) => {
          const currentVal = preferences[category.key as keyof PreferenceState] ?? "";
          const savedVal   = savedPreferences[category.key as keyof PreferenceState] ?? "";
          const isDirty    = currentVal !== savedVal;

          const currentIdx   = currentVal ? category.options.indexOf(currentVal) : -1;
          const currentLabel = currentIdx >= 0 ? category.displayLabels[currentIdx] : currentVal;
          const currentIcon  = currentIdx >= 0 ? category.optionIcons[currentIdx] : "";

          const dropdownOptions = category.options.map((opt, i) => ({
            value: opt,
            icon: category.optionIcons[i],
            label: category.displayLabels[i],
          }));

          return (
            <div
              key={category.key}
              className="rounded-2xl p-5 flex flex-col gap-4"
              style={{
                background: "var(--bg-surface, #111117)",
                border: isDirty
                  ? "1.5px solid rgba(224,62,82,0.55)"
                  : "1.5px solid var(--border, #1e1e2a)",
                transition: "border-color 0.15s",
              }}
            >
              {/* Card title */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xl">{category.icon}</span>
                  <h3 className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>
                    {category.label}
                  </h3>
                </div>
                {isDirty && currentVal && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider rounded-full px-2 py-0.5"
                    style={{ background: "rgba(224,62,82,0.15)", color: "#e03e52" }}>
                    unsaved
                  </span>
                )}
              </div>

              {/* Custom dropdown */}
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor={`pref-${category.key}`}
                  className="text-xs font-medium"
                  style={{ color: "var(--text-muted)" }}
                >
                  Change preference:
                </label>

                <CustomDropdown
                  id={`pref-${category.key}`}
                  value={currentVal}
                  options={dropdownOptions}
                  isDirty={isDirty}
                  onChange={(val) => handleChange(category.key, val)}
                  ariaLabel={`Select ${category.label}`}
                />

                {isDirty && currentVal && currentVal !== savedVal && (
                  <p className="text-xs flex items-center gap-1.5 mt-0.5" style={{ color: "#e03e52" }}>
                    <span>↳ will update to:</span>
                    <span className="font-semibold">{currentIcon} {currentLabel}</span>
                  </p>
                )}
                {isDirty && !currentVal && savedVal && (
                  <p className="text-xs mt-0.5" style={{ color: "rgba(239,68,68,0.8)" }}>
                    ↳ will clear this preference
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Empty State ─────────────────────────────────────────────────── */}
      {!loading && savedCount === 0 && !Object.values(preferences).some(Boolean) && (
        <div className="card flex flex-col items-center gap-4 py-16 text-center mt-6">
          <span className="text-5xl">🎯</span>
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            No preferences set yet
          </h2>
          <p className="text-sm max-w-md" style={{ color: "var(--text-muted)" }}>
            Use the dropdowns above to set your travel preferences, then hit{" "}
            <strong>Save Preferences</strong> to personalise every trip recommendation.
          </p>
        </div>
      )}

      {/* ── Sticky save bar ─────────────────────────────────────────────── */}
      {hasChanges && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-4 rounded-2xl px-6 py-3 shadow-2xl"
          style={{
            background: "rgba(17,17,23,0.95)",
            border: "1px solid rgba(224,62,82,0.4)",
            backdropFilter: "blur(12px)",
            zIndex: 50,
          }}
        >
          <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            You have unsaved changes
          </p>
          <button type="button" onClick={handleReset} disabled={saving}
            className="btn btn-ghost text-sm py-1 px-3">
            Discard
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary text-sm py-1 px-4"
            style={{ background: "linear-gradient(135deg, #e03e52, #ff5c75)" }}
          >
            {saving ? "Saving…" : "Save Now"}
          </button>
        </div>
      )}
    </div>
  );
}
