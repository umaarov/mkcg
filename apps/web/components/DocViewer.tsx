"use client";
import { useEffect, useRef, useState } from "react";
import { withToken } from "@/lib/api";

export type Hl = { page: number; bbox: number[] | null; tone?: "accent" | "warn" | "bad" } | null;

export function DocViewer({ cid, docId, pages, pageSizes, page, onPage, hl }: {
  cid: string; docId: number; pages: number; pageSizes: number[][]; page: number; onPage: (p: number) => void; hl: Hl;
}) {
  const [loaded, setLoaded] = useState(false);
  const [dim, setDim] = useState({ w: 1, h: 1 });
  const wrap = useRef<HTMLDivElement>(null);
  useEffect(() => setLoaded(false), [cid, docId, page]);
  useEffect(() => {
    if (hl && hl.bbox && hl.page === page && wrap.current && loaded) {
      const sz = pageSizes[page] || [595, 842];
      const y = (hl.bbox[1] / sz[1]) * dim.h;
      wrap.current.scrollTo({ top: Math.max(0, y - 120), behavior: "smooth" });
    }
  }, [hl, page, loaded, dim, pageSizes]);
  const sz = pageSizes[page] || [595, 842];
  const tone = hl?.tone === "bad" ? "var(--bad)" : hl?.tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-2 flex items-center justify-between text-[12px] text-muted">
        <div className="flex items-center gap-1">
          <button className="rounded border border-line px-2 py-0.5 hover:bg-surface-2 disabled:opacity-30" disabled={page <= 0} onClick={() => onPage(page - 1)} aria-label="previous page">‹</button>
          <span className="tnum px-1">{page + 1} / {pages}</span>
          <button className="rounded border border-line px-2 py-0.5 hover:bg-surface-2 disabled:opacity-30" disabled={page >= pages - 1} onClick={() => onPage(page + 1)} aria-label="next page">›</button>
        </div>
        <span>{hl?.bbox && hl.page !== page ? `highlight on page ${hl.page + 1}` : ""}</span>
      </div>
      <div ref={wrap} className="relative min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-surface-2 scroll-thin">
        <div className="relative mx-auto" style={{ width: "100%" }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={withToken(`/api/cases/${cid}/docs/${docId}/page/${page}.png`)} alt={`page ${page + 1}`} className="block w-full select-none"
            onLoad={(e) => { const i = e.currentTarget; setDim({ w: i.clientWidth, h: i.clientHeight }); setLoaded(true); }} />
          {!loaded && <div className="skeleton absolute inset-0" />}
          {loaded && hl?.bbox && hl.page === page && (
            <div className="pointer-events-none absolute rounded-[3px] transition-all duration-200"
              style={{
                left: `${(hl.bbox[0] / sz[0]) * 100 - 0.6}%`, top: `${(hl.bbox[1] / sz[1]) * 100 - 0.25}%`,
                width: `${((hl.bbox[2] - hl.bbox[0]) / sz[0]) * 100 + 1.2}%`, height: `${((hl.bbox[3] - hl.bbox[1]) / sz[1]) * 100 + 0.5}%`,
                background: `color-mix(in srgb, ${tone} 18%, transparent)`, outline: `2px solid ${tone}`,
              }} />
          )}
        </div>
      </div>
    </div>
  );
}
