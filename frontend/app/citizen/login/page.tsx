"use client";

/**
 * app/citizen/login/page.tsx — full-page citizen login (D-032).
 * Same parliament backdrop as the authority login. One wide card, two
 * columns: left = intro + how-it-works steps, right = Aadhaar → OTP →
 * login. Vertically and horizontally centered in the viewport.
 *
 * Honesty kept minimal: a single small note — not "demo" on every line.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { citizenApi, setCitizenSession, type CitizenSession } from "@/lib/citizen-api";

export default function CitizenLoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<"aadhaar" | "otp">("aadhaar");
  const [aadhaar, setAadhaar] = useState("");
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const aadhaarOk = /^\d{12}$/.test(aadhaar);
  const otpOk = /^\d{6}$/.test(otp);

  async function submitOtp(e: React.FormEvent) {
    e.preventDefault();
    if (!otpOk || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await citizenApi.login(aadhaar, otp);
      const s: CitizenSession = { token: res.token, maskedId: res.masked_id };
      setCitizenSession(s);
      router.push("/citizen?tab=feed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  }

  return (
    <div className="hero-parliament flex min-h-screen flex-col">
      <div className="flex justify-center px-4 pt-8">
        <Link href="/citizen" className="text-sm font-semibold text-white/80 hover:text-white">
          ← Back to the citizen portal
        </Link>
      </div>

      {/* True center: flex-1 + items-center */}
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="panel grid w-full max-w-3xl grid-cols-1 overflow-hidden md:grid-cols-2">
          {/* ── Left: intro + steps ──────────────────────────────────── */}
          <div className="flex flex-col justify-center gap-5 bg-primary-tint/60 p-8">
            <div>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/theme/Logo-english.png" alt="PARAKH" className="h-11" />
              <h1 className="mt-4 font-display text-2xl font-bold leading-tight text-primary">
                Your voice on
                <br />
                public works
              </h1>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                See what your constituency&apos;s MPLADS funds are building — and
                tell the oversight system what concerns you.
              </p>
            </div>

            <ol className="space-y-3.5">
              <li className="flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                  1
                </span>
                <div>
                  <p className="text-sm font-bold text-foreground">
                    Browse &amp; explore
                  </p>
                  <p className="text-xs leading-snug text-muted">
                    The feed, map and dossiers are open to everyone.
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                  2
                </span>
                <div>
                  <p className="text-sm font-bold text-foreground">
                    Log in with Aadhaar OTP
                  </p>
                  <p className="text-xs leading-snug text-muted">
                    One identity, one vote per work — that&apos;s the anti-spam
                    guarantee.
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-bold text-white">
                  3
                </span>
                <div>
                  <p className="text-sm font-bold text-foreground">
                    Upvote, report, rate
                  </p>
                  <p className="text-xs leading-snug text-muted">
                    Your reason joins the combined citizen signal on the
                    work&apos;s page.
                  </p>
                </div>
              </li>
            </ol>

            <p className="border-t border-brd pt-3 text-[11px] leading-snug text-faint">
              Verification is simulated for this prototype (UIDAI integration in
              production); only a one-way hash is stored.
            </p>
          </div>

          {/* ── Right: Aadhaar → OTP → login ─────────────────────────── */}
          <div className="flex flex-col justify-center p-8">
            {step === "aadhaar" ? (
              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (aadhaarOk) setStep("otp");
                }}
              >
                <div>
                  <h2 className="font-display text-lg font-bold text-primary">
                    Log in
                  </h2>
                  <p className="mt-0.5 text-xs text-muted">
                    Step 1 of 2 — enter your Aadhaar number
                  </p>
                </div>
                <input
                  autoFocus
                  inputMode="numeric"
                  maxLength={12}
                  placeholder="12-digit Aadhaar"
                  value={aadhaar}
                  onChange={(e) => setAadhaar(e.target.value.replace(/\D/g, "").slice(0, 12))}
                  className="w-full rounded-lg border border-brd bg-surface px-3.5 py-3 text-center font-mono text-lg tracking-[0.25em] focus:border-primary focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={!aadhaarOk}
                  className="btn-primary w-full py-3 text-sm disabled:opacity-40"
                >
                  Send OTP
                </button>
                <p className="text-center text-[11px] text-faint">
                  You&apos;ll receive a 6-digit OTP on the linked mobile.
                </p>
              </form>
            ) : (
              <form className="space-y-4" onSubmit={submitOtp}>
                <div>
                  <h2 className="font-display text-lg font-bold text-primary">
                    Verify OTP
                  </h2>
                  <p className="mt-0.5 text-xs text-muted">
                    Step 2 of 2 — sent to your Aadhaar-linked mobile
                  </p>
                </div>
                <input
                  autoFocus
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="••••••"
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  className="w-full rounded-lg border border-brd bg-surface px-3.5 py-3 text-center font-mono text-2xl tracking-[0.5em] focus:border-primary focus:outline-none"
                />
                {error && (
                  <p className="rounded-lg border border-high/40 bg-high/10 px-3 py-2 text-xs font-semibold text-high">
                    {error}
                  </p>
                )}
                <button
                  type="submit"
                  disabled={!otpOk || busy}
                  className="btn-primary w-full py-3 text-sm disabled:opacity-40"
                >
                  {busy ? "Verifying…" : "Log in"}
                </button>
                <button
                  type="button"
                  onClick={() => setStep("aadhaar")}
                  className="w-full text-center text-xs text-muted underline"
                >
                  ← Change Aadhaar number
                </button>
              </form>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
