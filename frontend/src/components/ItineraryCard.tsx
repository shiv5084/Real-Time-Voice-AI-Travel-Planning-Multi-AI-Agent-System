"use client";

interface Activity {
  time: string;
  title: string;
  description?: string;
  location?: string;
  duration?: string;
  cost?: number;
  category?: "transport" | "attraction" | "meal" | "accommodation" | "other";
}

interface DayPlan {
  day: number;
  date?: string;
  title?: string;
  activities: Activity[];
}

interface ItineraryCardProps {
  day: DayPlan;
  defaultExpanded?: boolean;
  className?: string;
}

const CATEGORY_ICONS: Record<string, string> = {
  transport:     "🚇",
  attraction:    "🏛️",
  meal:          "🍽️",
  accommodation: "🏨",
  other:         "📍",
};

const CATEGORY_COLOR: Record<string, string> = {
  transport:     "var(--info)",
  attraction:    "var(--accent)",
  meal:          "var(--warning)",
  accommodation: "var(--success)",
  other:         "var(--text-muted)",
};

export default function ItineraryCard({
  day,
  defaultExpanded = false,
  className = "",
}: ItineraryCardProps) {
  return (
    <details
      open={defaultExpanded}
      className={`card overflow-hidden p-0 ${className}`}
      aria-label={`Day ${day.day}${day.title ? `: ${day.title}` : ""}`}
    >
      {/* Summary / header */}
      <summary
        className="flex cursor-pointer list-none items-center justify-between p-4 select-none"
        style={{ borderBottom: "1px solid var(--border)" }}
        aria-expanded={defaultExpanded}
      >
        <div className="flex items-center gap-3">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold"
            style={{ background: "var(--accent-muted)", color: "var(--accent)" }}
            aria-hidden="true"
          >
            {day.day}
          </span>
          <div>
            <p className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {day.title ?? `Day ${day.day}`}
            </p>
            {day.date && (
              <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                <time dateTime={day.date}>{day.date}</time>
              </p>
            )}
          </div>
        </div>
        <span
          className="text-xs"
          style={{ color: "var(--text-muted)" }}
          aria-hidden="true"
        >
          {day.activities.length} activities ▾
        </span>
      </summary>

      {/* Activity list */}
      <ol className="divide-y px-4 py-2" style={{ borderColor: "var(--border)" }}>
        {day.activities.map((act, idx) => {
          const cat = act.category ?? "other";
          return (
            <li key={idx} className="flex gap-3 py-3">
              {/* Time column */}
              <div
                className="w-16 shrink-0 text-right text-xs"
                style={{ color: "var(--text-muted)", paddingTop: "2px" }}
              >
                {act.time}
              </div>

              {/* Icon */}
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-base"
                style={{ background: `${CATEGORY_COLOR[cat]}22` }}
                aria-hidden="true"
              >
                {CATEGORY_ICONS[cat]}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--text-primary)" }}>
                  {act.title}
                </p>
                {act.description && (
                  <p className="mt-0.5 text-xs leading-relaxed" style={{ color: "var(--text-secondary)" }}>
                    {act.description}
                  </p>
                )}
                <div className="mt-1 flex flex-wrap gap-3">
                  {act.location && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      📍 {act.location}
                    </span>
                  )}
                  {act.duration && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      ⏱ {act.duration}
                    </span>
                  )}
                  {act.cost != null && act.cost > 0 && (
                    <span className="text-xs" style={{ color: "var(--text-muted)" }}>
                      💰 ${(typeof act.cost === "number" ? act.cost : 0).toFixed(0)}
                    </span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </details>
  );
}
