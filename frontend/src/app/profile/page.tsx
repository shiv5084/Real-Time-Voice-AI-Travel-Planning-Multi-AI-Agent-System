"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { signOut } from "@/lib/auth";

interface UserPreferences {
  food_preferences?: string[];
  accommodation_style?: string;
  transport_preference?: string;
  activity_level?: "low" | "moderate" | "high";
  budget_style?: "budget" | "moderate" | "luxury";
  crowd_tolerance?: "low" | "moderate" | "high";
  dietary_restrictions?: string[];
}

interface UserProfile {
  id: string;
  email: string;
  full_name?: string;
  preferences: UserPreferences;
  trip_count: number;
  member_since?: string;
}

const PREF_OPTIONS = {
  accommodation_style: ["hostel", "budget hotel", "mid-range hotel", "boutique hotel", "luxury hotel"],
  transport_preference: ["walking", "public transit", "rental car", "taxis/rideshare", "mixed"],
  activity_level: ["low", "moderate", "high"],
  budget_style: ["budget", "moderate", "luxury"],
  crowd_tolerance: ["low", "moderate", "high"],
};

export default function ProfilePage() {
  const [profile, setProfile]   = useState<UserProfile | null>(null);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [saved, setSaved]       = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [prefs, setPrefs]       = useState<UserPreferences>({});

  useEffect(() => {
    api.get<UserProfile>("/api/profile")
      .then((p) => {
        setProfile(p);
        setPrefs(p.preferences ?? {});
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.put("/api/profile/preferences", prefs);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-10" aria-label="Loading profile">
        <div className="skeleton mb-4 h-10 w-1/3 rounded-xl" />
        <div className="skeleton h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            Profile
          </h1>
          {profile?.email && (
            <p className="text-sm" style={{ color: "var(--text-muted)" }}>
              {profile.email}
              {profile.trip_count > 0 && ` · ${profile.trip_count} trips`}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={signOut}
          className="btn btn-ghost text-sm"
          aria-label="Sign out"
        >
          Sign Out
        </button>
      </div>

      {error && (
        <div className="card mb-6" role="alert" style={{ borderColor: "rgba(239,68,68,0.4)" }}>
          <p className="text-sm" style={{ color: "var(--error)" }}>{error}</p>
        </div>
      )}

      {/* Preferences */}
      <section className="card flex flex-col gap-6" aria-label="Travel preferences">
        <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          Travel Preferences
        </h2>

        {(Object.keys(PREF_OPTIONS) as Array<keyof typeof PREF_OPTIONS>).map((key) => (
          <div key={key}>
            <label htmlFor={`pref-${key}`} className="capitalize">
              {key.replace(/_/g, " ")}
            </label>
            <select
              id={`pref-${key}`}
              className="input"
              value={(prefs[key as keyof UserPreferences] as string) ?? ""}
              onChange={(e) => setPrefs((prev) => ({ ...prev, [key]: e.target.value }))}
              aria-label={key.replace(/_/g, " ")}
            >
              <option value="">— no preference —</option>
              {PREF_OPTIONS[key].map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>
        ))}

        <div>
          <label htmlFor="dietary">Dietary restrictions (comma-separated)</label>
          <input
            id="dietary"
            type="text"
            className="input"
            value={(prefs.dietary_restrictions ?? []).join(", ")}
            onChange={(e) =>
              setPrefs((prev) => ({
                ...prev,
                dietary_restrictions: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              }))
            }
            placeholder="e.g. vegetarian, gluten-free"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn btn-primary"
            aria-label="Save preferences"
          >
            {saving ? "Saving…" : "Save Preferences"}
          </button>
          {saved && (
            <span className="text-sm" role="status" style={{ color: "var(--success)" }}>
              ✓ Saved
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
