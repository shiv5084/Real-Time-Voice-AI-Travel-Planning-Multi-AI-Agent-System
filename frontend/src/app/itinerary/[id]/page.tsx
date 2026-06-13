"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ItineraryCard from "@/components/ItineraryCard";
import BudgetChart, { type BudgetCategory } from "@/components/BudgetChart";
import { api, downloadFile } from "@/lib/api";

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

interface Itinerary {
  id: string;
  destination: string;
  startDate?: string;
  endDate?: string;
  days: DayPlan[];
  budget?: {
    total: number;
    currency: string;
    breakdown: BudgetCategory[];
    limit?: number;
    compliance?: "within_budget" | "warning" | "over_budget";
    recommendations?: string[];
  };
  warnings?: string[];
}

export default function ItineraryPage() {
  const { id } = useParams<{ id: string }>();
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);
  const [emailing, setEmailing]   = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  useEffect(() => {
    if (!id) return;
    api.get<Itinerary>(`/api/itineraries/${id}`)
      .then(setItinerary)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDownloadPDF = async () => {
    try {
      await downloadFile(`/api/itineraries/${id}/pdf`, `itinerary-${id}.pdf`, true);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "PDF download failed");
    }
  };

  const handleSendEmail = async () => {
    setEmailing(true);
    try {
      await api.post(`/api/itineraries/${id}/email`);
      setEmailSent(true);
      setTimeout(() => setEmailSent(false), 4000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Email failed");
    } finally {
      setEmailing(false);
    }
  };

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10" aria-label="Loading itinerary">
        <div className="skeleton mb-6 h-10 w-2/3 rounded-xl" />
        <div className="skeleton mb-4 h-48 rounded-xl" />
        <div className="skeleton mb-4 h-48 rounded-xl" />
      </div>
    );
  }

  if (error || !itinerary) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 text-center">
        <p className="text-sm" role="alert" style={{ color: "var(--error)" }}>
          {error ?? "Itinerary not found"}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      {/* Header */}
      <div className="mb-8">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 40, marginBottom: 16 }}>
          <div>
            <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>Destination</p>
            <h1 className="text-2xl font-bold" style={{ color: "var(--text-primary)", margin: 0 }}>
              📍 {itinerary.destination || "TBD"}
            </h1>
          </div>
          {(() => {
            const startDateVal = itinerary.startDate || (itinerary.days && itinerary.days[0]?.date);
            let endDateVal = itinerary.endDate || (itinerary.days && itinerary.days[itinerary.days.length - 1]?.date);
            if (startDateVal && (!endDateVal || endDateVal === startDateVal) && itinerary.days && itinerary.days.length > 1) {
              endDateVal = calculateEndDate(startDateVal, itinerary.days.length);
            }
            const dateRangeStr = startDateVal && endDateVal ? `${startDateVal} - ${endDateVal}` : startDateVal || endDateVal || "";
            return (
              <div>
                <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-muted)", marginBottom: 4 }}>start date - end date</p>
                <p className="text-lg font-semibold" style={{ color: "var(--text-primary)", margin: 0 }}>
                  🗓 {dateRangeStr || "TBD"}
                </p>
              </div>
            );
          })()}
        </div>

        {/* Action buttons */}
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleDownloadPDF}
            className="btn btn-ghost text-sm"
            aria-label="Download PDF report"
          >
            📄 Download PDF
          </button>
          <button
            type="button"
            onClick={handleSendEmail}
            disabled={emailing || emailSent}
            className="btn btn-ghost text-sm"
            aria-label="Email itinerary"
          >
            {emailSent ? "✓ Sent!" : emailing ? "Sending…" : "📧 Send Email"}
          </button>
        </div>
      </div>

      {/* Warnings */}
      {itinerary.warnings && itinerary.warnings.length > 0 && (
        <div
          className="card mb-6"
          role="alert"
          aria-label="Planning warnings"
          style={{ borderColor: "rgba(245,158,11,0.4)" }}
        >
          <h2 className="mb-2 text-sm font-semibold" style={{ color: "var(--warning)" }}>
            ⚠ Warnings
          </h2>
          <ul className="list-inside list-disc space-y-1">
            {itinerary.warnings.map((w, i) => (
              <li key={i} className="text-xs" style={{ color: "var(--text-secondary)" }}>
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Day cards */}
      <section aria-label="Day-by-day itinerary">
        <h2 className="mb-4 text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          Day-by-Day Plan
        </h2>
        <div className="flex flex-col gap-3">
          {itinerary.days.map((day) => (
            <ItineraryCard
              key={day.day}
              day={day}
              defaultExpanded={day.day === 1}
            />
          ))}
        </div>
      </section>

      {/* Budget chart */}
      {itinerary.budget && (
        <section className="mt-8" aria-label="Budget breakdown">
          <h2 className="mb-4 text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            Budget Overview
          </h2>
          {(() => {
            const comp = itinerary.budget?.compliance || "within_budget";
            const limit = itinerary.budget?.limit;
            const recommendations = itinerary.budget?.recommendations || [];
            
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
              <div style={{ display: "flex", flexDirection: "column", gap: 16, marginBottom: 20 }}>
                <div
                  style={{
                    background: bgColor,
                    border: `1px solid ${borderColor}`,
                    borderRadius: 12,
                    padding: "16px 20px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <div>
                    <p style={{ fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)", margin: 0 }}>
                      Budget Status
                    </p>
                    {limit && limit > 0 && (
                      <p style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 600, margin: "4px 0 0" }}>
                        Budget Limit: ${Number(limit).toFixed(0)}
                      </p>
                    )}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span style={{ fontSize: 14, fontWeight: 700, color: textColor, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                      {statusText}
                    </span>
                  </div>
                </div>

                {comp === "over_budget" && recommendations.length > 0 && (
                  <div
                    style={{
                      background: "rgba(239, 68, 68, 0.04)",
                      border: "1px dashed rgba(239, 68, 68, 0.3)",
                      borderRadius: 12,
                      padding: "16px 20px",
                    }}
                  >
                    <p style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "#ef4444", marginBottom: 10, marginTop: 0 }}>
                      💡 Suggested Budget Adjustments
                    </p>
                    <ul style={{ paddingLeft: 20, margin: 0, fontSize: 13, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 6 }}>
                      {recommendations.map((rec, rIdx) => (
                        <li key={rIdx}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })()}
          <BudgetChart
            categories={itinerary.budget.breakdown}
            total={itinerary.budget.total}
            currency={itinerary.budget.currency}
          />
        </section>
      )}
    </div>
  );
}
