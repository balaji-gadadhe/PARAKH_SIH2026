"use client";

/**
 * app/login/page.tsx — demo login + identity picker.
 * web-flow.md: 4 role portals; auth is DEMO ONLY (no verification).
 * After login: MoSPI goes straight to the dashboard; MP / SNO / DM pick
 * their identity from REAL backend data (731 MPs, states, constituencies).
 *
 * Scope travels via query params, e.g. /dashboard?role=mp&mp=Name —
 * refresh-safe and shareable during the team demo.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { api, type MpSummary } from "@/lib/api";

const ROLE_LABELS: Record<string, string> = {
  mospi: "MoSPI / Central Ministry",
  mp: "Hon'ble MP",
  sno: "State Nodal Officer",
  dm: "District Magistrate",
};

type Mode = "login" | "pick-mp" | "pick-state" | "pick-district";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-background" />}>
      <LoginInner />
    </Suspense>
  );
}

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const role = params.get("role") ?? "mospi";

  const [mode, setMode] = useState<Mode>("login");
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");

  // Picker state (fetched from the real backend)
  const [mps, setMps] = useState<MpSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "login") return;
    api
      .listMps({ sort: "works_desc" })
      .then((r) => setMps(r.items))
      .catch((e) => setError(String(e)));
  }, [mode]);

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    // Demo auth: no verification, per web-flow.md
    if (role === "mp") setMode("pick-mp");
    else if (role === "sno") setMode("pick-state");
    else if (role === "dm") setMode("pick-district");
    else router.push("/dashboard?role=mospi");
  }

  function goDash(extra: string) {
    router.push(`/dashboard?role=${role}${extra}`);
  }

  /* ─── Identity pickers (real backend data) ─────────────────────────── */

  const states = useMemo(() => {
    if (!mps) return [];
    const seen = new Map<string, number>();
    for (const m of mps) seen.set(m.state, (seen.get(m.state) ?? 0) + 1);
    return [...seen.entries()]
      .map(([state, count]) => ({ state, count }))
      .sort((a, b) => a.state.localeCompare(b.state));
  }, [mps]);

  const filteredStates = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return states;
    return states.filter((s) => s.state.toLowerCase().includes(q));
  }, [states, query]);

  const filteredMps = useMemo(() => {
    if (!mps) return [];
    const q = query.trim().toLowerCase();
    const base =
      role === "dm"
        ? mps // DM picks a constituency; we show all and label it demo
        : mps;
    if (!q) return base.slice(0, 50);
    return base
      .filter(
        (m) =>
          m.mp_name.toLowerCase().includes(q) ||
          m.constituency.toLowerCase().includes(q) ||
          m.state.toLowerCase().includes(q)
      )
      .slice(0, 50);
  }, [mps, query, role]);

  /* ─── Login screen ─────────────────────────────────────────────────── */

  if (mode === "login") {
    return (
      <div className="hero-parliament flex min-h-screen flex-col">
        <div className="flex justify-center px-4 pt-10">
          <Link href="/" className="text-sm font-semibold text-white/80 hover:text-white">
            ← Back to homepage
          </Link>
        </div>
        <div className="flex flex-1 items-center justify-center px-4 py-10">
          <div className="panel w-full max-w-md p-8">
            <div className="flex flex-col items-center gap-2 text-center">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/theme/Logo-english.png" alt="PARAKH" className="h-14" />
              <p className="section-label mt-2">Official Stakeholder Login</p>
              <h1 className="font-display text-2xl font-bold text-primary">
                {ROLE_LABELS[role] ?? "Login"}
              </h1>
            </div>
            <form onSubmit={handleLogin} className="mt-6 space-y-4">
              <input
                value={user}
                onChange={(e) => setUser(e.target.value)}
                placeholder="Username / Official ID"
                className="w-full rounded-lg border border-brd bg-surface px-3.5 py-3 text-sm focus:border-primary focus:outline-none"
                autoComplete="off"
              />
              <input
                value={pass}
                onChange={(e) => setPass(e.target.value)}
                placeholder="Password"
                type="password"
                className="w-full rounded-lg border border-brd bg-surface px-3.5 py-3 text-sm focus:border-primary focus:outline-none"
              />
              <button type="submit" className="btn-primary w-full py-3 text-sm">
                Login
              </button>
            </form>
            <p className="mt-4 text-center text-xs text-muted">
              Demo authentication — any credentials are accepted. No real
              accounts exist.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2 border-t border-brd pt-4">
              {Object.entries(ROLE_LABELS).map(([k, label]) => (
                <Link
                  key={k}
                  href={`/login?role=${k}`}
                  className={`rounded-full border px-3 py-1 text-[11px] font-semibold transition-colors ${
                    k === role
                      ? "border-primary bg-primary-tint text-primary"
                      : "border-brd text-muted hover:bg-surface-2"
                  }`}
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  /* ─── Identity picker screen ───────────────────────────────────────── */

  const pickerTitle =
    mode === "pick-mp"
      ? "Select your constituency (MP)"
      : mode === "pick-state"
        ? "Select your state"
        : "Select your district — demo: constituency proxy used";

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="mx-auto w-full max-w-3xl px-4 py-10 sm:px-6">
        <Link href={`/login?role=${role}`} className="text-sm font-semibold text-primary hover:underline">
          ← Back
        </Link>

        <div className="panel mt-4 p-6 sm:p-8">
          <div className="flex items-center gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/theme/Logo-english.png" alt="PARAKH" className="h-12" />
            <div>
              <p className="section-label">{ROLE_LABELS[role] ?? "Login"}</p>
              <h1 className="font-display text-xl font-bold text-primary">{pickerTitle}</h1>
            </div>
          </div>

          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              mode === "pick-state"
                ? "Search states…"
                : "Search MP name, constituency or state…"
            }
            className="mt-6 w-full rounded-lg border border-brd bg-surface px-3.5 py-3 text-sm focus:border-primary focus:outline-none"
          />

          {error && (
            <p className="mt-3 text-sm" style={{ color: "var(--tier-critical)" }}>
              Backend unreachable — {error}
            </p>
          )}
          {!mps && !error && (
            <p className="mt-4 animate-pulse text-sm text-muted">
              Loading live roster…
            </p>
          )}

          <div className="mt-4 max-h-[420px] divide-y divide-brd overflow-y-auto rounded-lg border border-brd">
            {mode === "pick-state" &&
              filteredStates.map((s) => (
                <button
                  key={s.state}
                  onClick={() => goDash(`&state=${encodeURIComponent(s.state)}`)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-surface-2"
                >
                  <span className="font-semibold text-foreground">{s.state}</span>
                  <span className="text-xs text-muted">
                    {s.count.toLocaleString("en-IN")} MP{s.count === 1 ? "" : "s"}
                  </span>
                </button>
              ))}

            {mode !== "pick-state" &&
              filteredMps.map((m) => (
                <button
                  key={`${m.mp_name}-${m.constituency}`}
                  onClick={() =>
                    goDash(`&mp=${encodeURIComponent(m.mp_name)}`)
                  }
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm hover:bg-surface-2"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-semibold text-foreground">
                      {m.mp_name}
                    </span>
                    <span className="block truncate text-xs text-muted">
                      {m.constituency} · {m.state}
                    </span>
                  </span>
                  {mode === "pick-district" && (
                    <span className="disclaimer-chip shrink-0">demo proxy</span>
                  )}
                </button>
              ))}
          </div>

          {mps && mode === "pick-state" && filteredStates.length === 0 && (
            <p className="mt-4 text-sm text-muted">
              No state matches &ldquo;{query}&rdquo;.
            </p>
          )}

          {mps && (
            <p className="mt-3 text-xs text-faint">
              Showing up to 50 matches · live roster of {mps.length.toLocaleString("en-IN")} MPs
              from the MPLADS dataset
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
