"use client";
import { ReactNode } from "react";

export type Tone = "neutral" | "good" | "warn" | "bad" | "info" | "accent";
const TONES: Record<Tone, string> = {
  neutral: "bg-surface-2 text-ink-2 border-line",
  good: "bg-good-soft text-good border-transparent",
  warn: "bg-warn-soft text-warn border-transparent",
  bad: "bg-bad-soft text-bad border-transparent",
  info: "bg-info-soft text-info border-transparent",
  accent: "bg-accent-soft text-accent border-transparent",
};

export function Chip({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-5 whitespace-nowrap ${TONES[tone]}`}>
      {children}
    </span>
  );
}

export function Card({ children, className = "", pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <section className={`rounded-xl border border-line bg-surface ${pad ? "p-5" : ""} ${className}`}>{children}</section>;
}

export function H({ children, sub, right }: { children: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="serif text-[19px] leading-6 text-ink">{children}</h2>
        {sub && <p className="mt-0.5 text-[12.5px] text-muted max-w-[68ch]">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, type = "button", className = "", title }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "danger" | "soft"; disabled?: boolean; type?: "button" | "submit"; className?: string; title?: string;
}) {
  const v = {
    primary: "bg-accent text-accent-ink hover:opacity-90",
    ghost: "border border-line-2 text-ink hover:bg-surface-2",
    soft: "bg-accent-soft text-accent hover:opacity-80",
    danger: "bg-bad text-white hover:opacity-90",
  }[variant];
  return (
    <button type={type} title={title} onClick={onClick} disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-[13px] font-medium transition disabled:opacity-40 disabled:cursor-not-allowed ${v} ${className}`}>
      {children}
    </button>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone }) {
  const c = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "good" ? "text-good" : "text-ink";
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`serif tnum mt-0.5 text-[22px] leading-7 ${c}`}>{value}</div>
      {sub && <div className="text-[11.5px] text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; badge?: ReactNode }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div role="tablist" className="flex gap-1 overflow-x-auto border-b border-line scroll-thin">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`relative whitespace-nowrap px-3.5 py-2.5 text-[13px] transition ${value === t.id ? "text-ink font-medium" : "text-muted hover:text-ink"}`}>
          <span className="inline-flex items-center gap-1.5">{t.label}{t.badge}</span>
          {value === t.id && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded bg-accent" />}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ h = 16, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}

export function Bar({ value, max = 1, tone = "accent" }: { value: number; max?: number; tone?: "accent" | "bad" | "warn" | "good" }) {
  const c = { accent: "bg-accent", bad: "bg-bad", warn: "bg-warn", good: "bg-good" }[tone];
  return (
    <div className="h-1.5 w-full rounded-full bg-surface-2 overflow-hidden">
      <div className={`h-full rounded-full ${c}`} style={{ width: `${Math.max(0, Math.min(1, value / max)) * 100}%` }} />
    </div>
  );
}

export const outcomeTone = (o: string): Tone => (o === "PASS" ? "good" : o === "REFER" ? "warn" : "bad");
export const recTone = (r?: string | null): Tone => (r === "APPROVE" ? "good" : r === "REVIEW" ? "info" : r === "REFER" ? "warn" : r === "DECLINE" ? "bad" : "neutral");
export const bandTone = (b?: string | null): Tone => (b === "A" || b === "B" ? "good" : b === "C" ? "info" : b === "D" ? "warn" : b === "E" ? "bad" : "neutral");
