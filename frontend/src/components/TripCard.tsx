"use client";

import Link from "next/link";

export interface TripSummary {
  id: string;
  destination: string;
  startDate?: string;
  endDate?: string;
  status: "draft" | "planned" | "completed";
  thumbnailEmoji?: string;
  totalBudget?: number;
  currency?: string;
  daysCount?: number;
}

interface TripCardProps {
  trip: TripSummary;
  onDelete?: (id: string) => void;
  className?: string;
}

const STATUS_BADGE: Record<TripSummary["status"], { label: string; cls: string }> = {
  draft:     { label: "Draft",     cls: "badge-info" },
  planned:   { label: "Planned",   cls: "badge-accent" },
  completed: { label: "Completed", cls: "badge-success" },
};

export default function TripCard({ trip, onDelete, className = "" }: TripCardProps) {
  const badge = STATUS_BADGE[trip.status];
  const fmt = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: trip.currency ?? "USD",
    maximumFractionDigits: 0,
  });

  return (
    <article
      className={`card group relative flex flex-col gap-3 ${className}`}
      aria-label={`Trip to ${trip.destination}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <span
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-xl"
            style={{ background: "var(--bg-elevated)" }}
            aria-hidden="true"
          >
            {trip.thumbnailEmoji ?? "✈️"}
          </span>
          <div>
            <h3
              className="text-sm font-semibold leading-tight"
              style={{ color: "var(--text-primary)" }}
            >
              {trip.destination}
            </h3>
            {(trip.startDate || trip.endDate) && (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                {[trip.startDate, trip.endDate].filter(Boolean).join(" → ")}
              </p>
            )}
          </div>
        </div>
        <span className={`badge ${badge.cls} shrink-0`}>{badge.label}</span>
      </div>

      {/* Meta */}
      <div className="flex items-center gap-4 text-xs" style={{ color: "var(--text-muted)" }}>
        {trip.daysCount && <span>📅 {trip.daysCount} day{trip.daysCount !== 1 ? "s" : ""}</span>}
        {trip.totalBudget !== undefined && (
          <span>💰 {fmt.format(trip.totalBudget)}</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Link
          href={`/itinerary/${trip.id}`}
          className="btn btn-primary flex-1 text-xs"
          style={{ padding: "0.4rem 0.75rem" }}
          aria-label={`View itinerary for ${trip.destination}`}
        >
          View Itinerary →
        </Link>

        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(trip.id)}
            className="btn btn-ghost text-xs"
            style={{ padding: "0.4rem 0.75rem" }}
            aria-label={`Delete trip to ${trip.destination}`}
          >
            Delete
          </button>
        )}
      </div>
    </article>
  );
}
