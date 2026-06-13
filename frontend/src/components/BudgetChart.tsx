"use client";

import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface BudgetCategory {
  name: string;
  amount: number;
  color?: string;
}

interface BudgetChartProps {
  categories: BudgetCategory[];
  total?: number;
  currency?: string;
  className?: string;
}

const DEFAULT_COLORS = [
  "#6c63ff", // accent
  "#38bdf8", // info
  "#22c55e", // success
  "#f59e0b", // warning
  "#ef4444", // error
  "#a78bfa", // violet
  "#34d399", // emerald
  "#fb923c", // orange
];

export default function BudgetChart({
  categories,
  total,
  currency = "USD",
  className = "",
}: BudgetChartProps) {
  if (!categories.length) {
    return (
      <div
        className={`card flex items-center justify-center ${className}`}
        style={{ minHeight: "200px" }}
        aria-label="Budget breakdown"
      >
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          No budget data available.
        </p>
      </div>
    );
  }

  const data = categories.map((c, i) => ({
    name:   c.name,
    value:  c.amount,
    color:  c.color ?? DEFAULT_COLORS[i % DEFAULT_COLORS.length],
  }));

  const calculatedTotal =
    total ?? categories.reduce((s, c) => s + c.amount, 0);

  const fmt = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  });

  return (
    <div
      className={`card ${className}`}
      aria-label="Budget breakdown chart"
    >
      <h3 className="mb-1 text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
        Budget Breakdown
      </h3>
      <p className="mb-4 text-xs" style={{ color: "var(--text-muted)" }}>
        Total: {fmt.format(calculatedTotal)}
      </p>

      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={100}
            paddingAngle={3}
            dataKey="value"
            aria-label="Budget pie chart"
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.color}
                stroke="transparent"
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number) => [fmt.format(value), "Amount"]}
            contentStyle={{
              background:   "var(--bg-elevated)",
              border:       "1px solid var(--border)",
              borderRadius: "var(--radius-md)",
              color:        "var(--text-primary)",
              fontSize:     "0.8125rem",
            }}
          />
          <Legend
            iconSize={10}
            iconType="circle"
            formatter={(value) => (
              <span style={{ color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                {value}
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>

      {/* Table summary */}
      <table className="mt-2 w-full text-xs" aria-label="Budget table">
        <caption className="sr-only">Budget category breakdown</caption>
        <thead>
          <tr>
            <th className="pb-1 text-left font-medium" style={{ color: "var(--text-muted)" }}>Category</th>
            <th className="pb-1 text-right font-medium" style={{ color: "var(--text-muted)" }}>Amount</th>
            <th className="pb-1 text-right font-medium" style={{ color: "var(--text-muted)" }}>%</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.name}>
              <td className="py-0.5 flex items-center gap-1.5" style={{ color: "var(--text-primary)" }}>
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: item.color }}
                  aria-hidden="true"
                />
                {item.name}
              </td>
              <td className="py-0.5 text-right" style={{ color: "var(--text-secondary)" }}>
                {fmt.format(item.value)}
              </td>
              <td className="py-0.5 text-right" style={{ color: "var(--text-muted)" }}>
                {((item.value / calculatedTotal) * 100).toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
