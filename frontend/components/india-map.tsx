"use client";

/**
 * components/india-map.tsx — India states choropleth (D-031 Step 2c, rev 2).
 *
 * Zero-dependency SVG choropleth: inline equirectangular projection over the
 * bundled offline geometry (public/geo/india-states.geojson — 28 KB, 36
 * state/UT features, property `st_nm`; names verified to match the dataset).
 *
 * Coloring (user-selected criteria): **weighted flag intensity** —
 *   intensity = (4×CRITICAL + 2×HIGH + 1×MEDIUM) / max over all states
 * A state is colored by how concentrated its weighted flag load is relative
 * to the worst state, NOT merely by whether it has a worst-tier work.
 * Risk colors stay semantic (risk colors are data, not brand — D-023).
 *
 * Interaction: hover = float effect + tooltip with the state's numbers;
 * click fires onSelect(state). Corner index explains the color criteria.
 * Honesty: numbers come from /api/dashboard/states over the frozen batch —
 * aggregate risk indicators, not findings.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import type { StateRiskItem } from "@/lib/api";

// ─── Minimal GeoJSON types (bundled file only needs these) ──────────────────

interface GeoFeature {
  type: "Feature";
  properties: { st_nm: string };
  geometry: {
    type: "Polygon" | "MultiPolygon";
    coordinates: number[][][] | number[][][][];
  };
}
interface GeoCollection {
  type: "FeatureCollection";
  features: GeoFeature[];
}

/** Module-level cache — the geometry never changes, fetch it once per tab. */
let geoCache: GeoCollection | null = null;

// ─── Weighted intensity (shared with the Overview ranking) ──────────────────

/**
 * Weighted flag load: severity-aware (CRITICAL weighs 4× HIGH, 2× MEDIUM).
 * Normalized against the worst state → 0..1 (0 = no flagged works at all).
 */
export function stateIntensity(s: StateRiskItem | undefined): number {
  if (!s) return 0;
  return 4 * s.critical + 2 * s.high + s.medium;
}

export function intensityBuckets(states: StateRiskItem[]): Map<string, number> {
  const max = Math.max(1e-9, ...states.map(stateIntensity));
  const m = new Map<string, number>();
  for (const s of states) m.set(s.state, stateIntensity(s) / max);
  return m;
}

// ─── Projection ──────────────────────────────────────────────────────────────

/**
 * Equirectangular projection with a fixed latitude-shrink factor (k = cos of
 * India's mean latitude ≈ 22°) so the map's aspect ratio looks right without
 * pulling in a projection library. Scale: 10 SVG units per degree.
 */
const K = Math.cos((22 * Math.PI) / 180);
const SCALE = 10;

function project(lon: number, lat: number, lonMin: number, latMax: number): [number, number] {
  return [(lon - lonMin) * K * SCALE, (latMax - lat) * SCALE];
}

function ringToPath(ring: number[][], lonMin: number, latMax: number): string {
  const pts = ring.map(([lon, lat]) => project(lon, lat, lonMin, latMax));
  if (pts.length === 0) return "";
  const head = `M${pts[0][0].toFixed(1)},${pts[0][1].toFixed(1)}`;
  const tail = pts
    .slice(1)
    .map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`)
    .join("");
  return `${head}${tail}Z`;
}

function featureToPath(f: GeoFeature, lonMin: number, latMax: number): string {
  const g = f.geometry;
  const polys: number[][][][] =
    g.type === "Polygon" ? [g.coordinates as number[][][]] : (g.coordinates as number[][][][]);
  return polys
    .map((poly) => poly.map((ring) => ringToPath(ring, lonMin, latMax)).join(""))
    .join("");
}

// ─── Intensity → color buckets ───────────────────────────────────────────────

interface TierStyle {
  color: string;
  opacity: number;
  label: string;
}

function bucketFor(s: StateRiskItem | undefined, intensity: number | undefined): TierStyle {
  if (!s || s.total_works === 0) return { color: "#E7E4DA", opacity: 0.7, label: "No works recorded" };
  if (intensity === undefined || intensity <= 0)
    return { color: "var(--tier-low)", opacity: 0.35, label: "No flagged works" };
  if (intensity <= 0.12) return { color: "var(--tier-medium)", opacity: 0.35, label: "Low flag load" };
  if (intensity <= 0.3) return { color: "var(--tier-medium)", opacity: 0.7, label: "Moderate flag load" };
  if (intensity <= 0.6) return { color: "var(--tier-high)", opacity: 0.85, label: "High flag load" };
  return { color: "var(--tier-critical)", opacity: 0.95, label: "Severe flag load" };
}

const INDEX_ROWS: { key: string; swatch: string; opacity: number }[] = [
  { key: "Severe flag load", swatch: "var(--tier-critical)", opacity: 0.95 },
  { key: "High", swatch: "var(--tier-high)", opacity: 0.85 },
  { key: "Moderate", swatch: "var(--tier-medium)", opacity: 0.7 },
  { key: "Low", swatch: "var(--tier-medium)", opacity: 0.35 },
  { key: "No flagged works", swatch: "var(--tier-low)", opacity: 0.35 },
  { key: "No works", swatch: "#E7E4DA", opacity: 0.7 },
];

// ─── Colour index card (rendered beside the map, not over it) ───────────────

/**
 * The map's colour criteria as a standalone card. Lives in the Overview's
 * side column (user call: the on-map overlay covered the eastern states).
 */
export function MapColourIndex() {
  return (
    <div className="rounded-xl border border-brd bg-surface p-4">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted">
        Colour index
      </p>
      <p className="mt-1 text-[10px] leading-snug text-faint">
        Weighted flag load: 4×CRITICAL + 2×HIGH + 1×MEDIUM, relative to the
        worst state
      </p>
      <div className="mt-2.5 space-y-1.5">
        {INDEX_ROWS.map((r) => (
          <span key={r.key} className="flex items-center gap-2 text-[10px] font-semibold text-muted">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm border border-white/60"
              style={{ background: r.swatch, opacity: r.opacity }}
            />
            {r.key}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── Component ───────────────────────────────────────────────────────────────

export function IndiaMap({
  data,
  loading = false,
  selected,
  onSelect,
}: {
  /** Per-state aggregation from GET /api/dashboard/states. */
  data: StateRiskItem[];
  loading?: boolean;
  /** Highlighted state (deep-linked selection). */
  selected?: string;
  /** Click handler — state name as it appears in the dataset. */
  onSelect?: (state: string) => void;
}) {
  const [geo, setGeo] = useState<GeoCollection | null>(geoCache);
  const [hovered, setHovered] = useState<string | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number; w: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Cache hit already populated state via the useState initializer — skip.
    if (geoCache) return;
    let alive = true;
    fetch("/geo/india-states.geojson")
      .then((r) => r.json())
      .then((d: GeoCollection) => {
        geoCache = d;
        if (alive) setGeo(d);
      })
      .catch(() => {
        /* render the list fallback below */
      });
    return () => {
      alive = false;
    };
  }, []);

  const byName = useMemo(() => {
    const m = new Map<string, StateRiskItem>();
    for (const s of data) m.set(s.state, s);
    return m;
  }, [data]);

  const intensity = useMemo(() => intensityBuckets(data), [data]);

  const { paths, viewBox } = useMemo(() => {
    if (!geo) return { paths: [] as { name: string; d: string }[], viewBox: "" };
    const lons: number[] = [];
    const lats: number[] = [];
    for (const f of geo.features) {
      const polys: number[][][][] =
        f.geometry.type === "Polygon"
          ? [f.geometry.coordinates as number[][][]]
          : (f.geometry.coordinates as number[][][][]);
      for (const poly of polys)
        for (const ring of poly)
          for (const [lon, lat] of ring) {
            lons.push(lon);
            lats.push(lat);
          }
    }
    const lonMin = Math.min(...lons) - 0.4;
    const lonMax = Math.max(...lons) + 0.4;
    const latMin = Math.min(...lats) - 0.4;
    const latMax = Math.max(...lats) + 0.4;
    const w = (lonMax - lonMin) * K * SCALE;
    const h = (latMax - latMin) * SCALE;
    return {
      paths: geo.features.map((f) => ({
        name: f.properties.st_nm,
        d: featureToPath(f, lonMin, latMax),
      })),
      viewBox: `0 0 ${w.toFixed(0)} ${h.toFixed(0)}`,
    };
  }, [geo]);

  const hoveredItem = hovered ? byName.get(hovered) : undefined;

  const onMove = (e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setTip({ x: e.clientX - rect.left, y: e.clientY - rect.top, w: rect.width });
  };

  return (
    <div
      ref={containerRef}
      className="relative mx-auto w-full max-w-[420px]"
      onMouseLeave={() => {
        setHovered(null);
        setTip(null);
      }}
    >
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-xl bg-surface/60 text-sm text-muted">
          Loading map…
        </div>
      )}

      {geo ? (
        <svg
          viewBox={viewBox}
          className="h-auto w-full"
          role="img"
          aria-label="India map — states colored by weighted flag intensity"
        >
          {paths.map((p) => {
            const s = byName.get(p.name);
            const t = bucketFor(s, intensity.get(p.name));
            const isSel = selected === p.name;
            return (
              <path
                key={p.name}
                d={p.d}
                fill={t.color}
                fillOpacity={isSel ? 1 : t.opacity}
                fillRule="evenodd"
                stroke={isSel ? "var(--foreground)" : "#FFFFFF"}
                strokeWidth={isSel ? 1.6 : 0.5}
                className="map-state-path cursor-pointer"
                role="button"
                aria-label={`${p.name} — ${s ? `${s.total_works.toLocaleString("en-IN")} works, ${s.high_critical} high or critical` : "no works recorded"}`}
                onMouseEnter={() => setHovered(p.name)}
                onMouseMove={onMove}
                onClick={() => onSelect?.(p.name)}
              />
            );
          })}
        </svg>
      ) : (
        !loading && (
          <p className="py-8 text-center text-sm text-muted">
            Map geometry unavailable — use the state ranking beside it.
          </p>
        )
      )}

      {/* Hover tooltip */}
      {hovered && tip && (
        <div
          className="pointer-events-none absolute z-20 w-52 rounded-lg border border-brd bg-surface p-3 shadow-[var(--shadow-modal)]"
          style={{
            left: Math.min(tip.x + 14, tip.w - 220),
            top: Math.max(tip.y - 10, 4),
          }}
        >
          <p className="text-xs font-bold text-foreground">{hovered}</p>
          {hoveredItem ? (
            <div className="mt-1.5 space-y-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-muted">Works</span>
                <span className="font-bold text-foreground">
                  {hoveredItem.total_works.toLocaleString("en-IN")}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">CRITICAL</span>
                <span className="font-bold text-critical">{hoveredItem.critical}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">HIGH</span>
                <span className="font-bold text-high">{hoveredItem.high}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">MEDIUM</span>
                <span className="font-bold text-medium">{hoveredItem.medium.toLocaleString("en-IN")}</span>
              </div>
              <div className="flex justify-between border-t border-brd pt-1">
                <span className="text-muted">Funds allocated</span>
                <span className="font-semibold text-foreground">
                  ₹{(hoveredItem.funds_allocated / 10000000).toFixed(1)} Cr
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">MPs flagged</span>
                <span className="font-semibold text-foreground">{hoveredItem.flagged_mps}</span>
              </div>
            </div>
          ) : (
            <p className="mt-1 text-[11px] text-muted">No works recorded</p>
          )}
          <p className="mt-1.5 border-t border-brd pt-1 text-[9px] text-faint">
            Click to inspect · frozen batch 2026-09-01
          </p>
        </div>
      )}
    </div>
  );
}
