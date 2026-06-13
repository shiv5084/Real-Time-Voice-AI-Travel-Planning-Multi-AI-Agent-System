"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TripCard, { type TripSummary } from "@/components/TripCard";
import { api } from "@/lib/api";
import { getSupabaseClient } from "@/lib/auth";

export default function DashboardPage() {
  const router = useRouter();
  const [trips, setTrips]     = useState<TripSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  useEffect(() => {
    // Auth guard: redirect to /login if not authenticated
    getSupabaseClient().auth.getSession().then(({ data }) => {
      if (!data.session) {
        router.replace("/login");
        return;
      }
      api.get<TripSummary[]>("/api/trips")
        .then(setTrips)
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    });
  }, [router]);

  const handleDelete = async (id: string) => {
    try {
      await api.delete(`/api/trips/${id}`);
      setTrips((prev) => prev.filter((t) => t.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
            My Trips
          </h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            {trips.length} trip{trips.length !== 1 ? "s" : ""} saved
          </p>
        </div>
        <Link href="/" className="btn btn-primary" aria-label="Plan a new trip">
          + New Trip
        </Link>
      </div>

      {/* States */}
      {loading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading trips">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-48 rounded-xl" aria-hidden="true" />
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="card text-center" role="alert" aria-live="polite">
          <p className="mb-4 text-sm" style={{ color: "var(--error)" }}>{error}</p>
          <button className="btn btn-ghost text-sm" onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && trips.length === 0 && (
        <div className="card flex flex-col items-center gap-4 py-16 text-center">
          <span className="text-5xl">🗺️</span>
          <h2 className="text-lg font-semibold" style={{ color: "var(--text-primary)" }}>
            No trips yet
          </h2>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Create your first AI-powered itinerary in seconds.
          </p>
          <Link href="/" className="btn btn-primary">
            Plan My First Trip
          </Link>
        </div>
      )}

      {!loading && !error && trips.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {trips.map((trip) => (
            <TripCard key={trip.id} trip={trip} onDelete={handleDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
