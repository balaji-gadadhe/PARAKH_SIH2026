"use client";

/**
 * components/charts.tsx — Recharts wrappers using the PARAKH palette.
 * Values shown exactly as served by the backend (no fabrication).
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RiskTier } from "@/lib/api";
import { TIER_HEX, TIER_ORDER, ACCENT_HEX } from "@/lib/theme";

const tooltipStyle = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  fontSize: 12,
  color: "var(--foreground)",
  boxShadow: "var(--shadow-card)",
};

/* ─── Risk tier donut ────────────────────────────────────────────────── */

export function TierDonut({
  counts,
  height = 220,
}: {
  counts: Partial<Record<RiskTier, number>>;
  height?: number;
}) {
  const data = TIER_ORDER.map((tier) => ({
    tier,
    count: counts[tier] ?? 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="tier"
          innerRadius="62%"
          outerRadius="88%"
          paddingAngle={2}
          stroke="none"
        >
          {data.map((d) => (
            <Cell key={d.tier} fill={TIER_HEX[d.tier]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value) => [Number(value).toLocaleString("en-IN"), ""]}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

/* ─── Horizontal bar list (states, MPs, agencies) ────────────────────── */

export function HBarList({
  data,
  height = 240,
  color = ACCENT_HEX,
}: {
  data: { label: string; value: number }[];
  height?: number;
  color?: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ right: 34 }}>
        <CartesianGrid
          horizontal={false}
          stroke="var(--border)"
          strokeDasharray="3 3"
        />
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey="label"
          width={120}
          tickLine={false}
          axisLine={false}
          tick={{ fontSize: 12, fill: "var(--muted)" }}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: "var(--surface-2)" }}
          formatter={(value) => [Number(value).toLocaleString("en-IN"), ""]}
        />
        <Bar dataKey="value" fill={color} radius={[0, 6, 6, 0]} barSize={14}>
          <LabelList
            dataKey="value"
            position="right"
            fontSize={11}
            fill="var(--muted)"
            formatter={(v) => Number(v).toLocaleString("en-IN")}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
