"use client";
import { mln } from "@/lib/format";

export function FlowChart({ months, inflow, outflow, lang }: { months: string[]; inflow: number[]; outflow: number[]; lang: string }) {
  const W = 560, H = 190, pl = 44, pb = 22, pt = 10;
  const max = Math.max(...inflow, ...outflow, 1) * 1.1;
  const bw = (W - pl) / months.length;
  const y = (v: number) => pt + (H - pt - pb) * (1 - v / max);
  const ticks = [0, 0.5, 1].map((f) => max * f / 1.1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="monthly inflow and outflow">
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeDasharray={i ? "3 3" : ""} />
          <text x={pl - 6} y={y(t) + 3} textAnchor="end" fontSize="9.5" fill="var(--muted)">{mln(t, lang)}</text>
        </g>
      ))}
      {months.map((m, i) => {
        const x = pl + i * bw;
        const w = bw * 0.34;
        return (
          <g key={m}>
            <rect x={x + bw * 0.12} y={y(inflow[i])} width={w} height={H - pb - y(inflow[i])} rx={2} fill="var(--accent)" />
            <rect x={x + bw * 0.12 + w + 3} y={y(outflow[i])} width={w} height={H - pb - y(outflow[i])} rx={2} fill="var(--line-2)" />
            <text x={x + bw * 0.5} y={H - 7} textAnchor="middle" fontSize="9.5" fill="var(--muted)">{m.slice(5)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function Spark({ values, w = 120, h = 32, color = "var(--accent)", baseline }: { values: number[]; w?: number; h?: number; color?: string; baseline?: number }) {
  if (!values.length) return null;
  const lo = Math.min(...values, baseline ?? Infinity), hi = Math.max(...values, baseline ?? -Infinity);
  const span = hi - lo || 1;
  const pts = values.map((v, i) => `${(i / Math.max(values.length - 1, 1)) * (w - 4) + 2},${h - 3 - ((v - lo) / span) * (h - 6)}`).join(" ");
  const by = baseline != null ? h - 3 - ((baseline - lo) / span) * (h - 6) : null;
  return (
    <svg width={w} height={h} className="overflow-visible">
      {by != null && <line x1={0} x2={w} y1={by} y2={by} stroke="var(--line-2)" strokeDasharray="3 3" />}
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts.split(" ").slice(-1)[0].split(",")[0]} cy={pts.split(" ").slice(-1)[0].split(",")[1]} r={2.4} fill={color} />
    </svg>
  );
}

export function HBars({ rows, fmt, tone }: { rows: { label: string; value: number; sub?: string }[]; fmt: (v: number) => string; tone?: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1e-9);
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5">
          <div className="truncate text-[12.5px] text-ink-2">{r.label}</div>
          <div className="tnum text-[12px] text-ink">{fmt(r.value)}</div>
          <div className="col-span-2 h-1.5 rounded-full bg-surface-2 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: tone || "var(--accent)" }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function Gauge({ value, bands, label }: { value: number; bands: number[]; label: string }) {
  // value = PD in 0..1, shown on a log-ish 0..70% track with band cut-offs
  const max = 0.7;
  const pos = Math.min(value / max, 1) * 100;
  const stops = [0, ...bands, max];
  const colors = ["var(--good)", "var(--good)", "var(--info)", "var(--warn)", "var(--bad)"];
  return (
    <div>
      <div className="relative h-2.5 rounded-full overflow-hidden flex">
        {stops.slice(0, -1).map((s, i) => (
          <div key={i} style={{ width: `${((Math.min(stops[i + 1], max) - s) / max) * 100}%`, background: colors[i], opacity: 0.35 }} />
        ))}
      </div>
      <div className="relative h-5">
        <div className="absolute -top-3 h-4 w-0.5 bg-ink" style={{ left: `${pos}%` }} />
        <div className="absolute top-2 -translate-x-1/2 text-[11px] text-ink tnum" style={{ left: `${Math.min(Math.max(pos, 6), 94)}%` }}>{label}</div>
      </div>
    </div>
  );
}

export function Calib({ points }: { points: { pred: number; obs: number }[] }) {
  const S = 180, p = 24;
  const mx = Math.max(...points.map((q) => Math.max(q.pred, q.obs)), 0.01) * 1.1;
  const X = (v: number) => p + (v / mx) * (S - p - 6);
  const Y = (v: number) => S - p - (v / mx) * (S - p - 6);
  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[220px]">
      <line x1={X(0)} y1={Y(0)} x2={X(mx)} y2={Y(mx)} stroke="var(--line-2)" strokeDasharray="3 3" />
      <polyline fill="none" stroke="var(--accent)" strokeWidth={1.6} points={points.map((q) => `${X(q.pred)},${Y(q.obs)}`).join(" ")} />
      {points.map((q, i) => <circle key={i} cx={X(q.pred)} cy={Y(q.obs)} r={2.6} fill="var(--accent)" />)}
      <text x={S / 2} y={S - 4} textAnchor="middle" fontSize="9" fill="var(--muted)">predicted</text>
      <text x={8} y={S / 2} fontSize="9" fill="var(--muted)" transform={`rotate(-90 8 ${S / 2})`} textAnchor="middle">observed</text>
    </svg>
  );
}
