#!/usr/bin/env python
"""
smoke_e2e.py -- PARAKH end-to-end smoke check (demo readiness).

One command to answer: "is this laptop demo-ready?"

What it does:
1. Boots the FastAPI backend on a scratch port against the committed demo data
   (D-027) -- no assumptions about servers already running. Reports whether the
   risk table was loaded from the committed .csv.gz or a locally regenerated
   plain CSV.
2. Asserts the FROZEN demo numbers (D-027, verified Session 11) on every
   endpoint group: dashboard KPIs, tier distribution, projects, alerts,
   MPs, agencies, plus the two card-reference worked examples
   (project 80673 and MP Shri Harbhajan Singh (2022-28)).
3. With --frontend: probes the running Next.js dev server's 10 demo routes
   for HTTP 200 (it does NOT start the dev server -- start it first with
   `npm run dev`).

Usage (from the repo root, SIH-2026/):
    python scripts/smoke_e2e.py
    python scripts/smoke_e2e.py --backend-url http://localhost:8000   # check an already-running backend
    python scripts/smoke_e2e.py --frontend                            # also probe http://localhost:3000
    python scripts/smoke_e2e.py --frontend-url http://localhost:3010  # probe a dev server on another port

Exit code 0 = demo-ready. 1 = at least one check failed. 2 = environment problem.
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import httpx
except ImportError:
    print("ERROR: httpx is not installed. Activate the venv and run:")
    print("    pip install -r requirements.txt")
    sys.exit(2)


# --- Frozen demo numbers (D-027; reproduced on fresh clones, Session 11) ----

TOTAL_WORKS = 86_976
TOTAL_MPS = 731
TIER_DIST = {"LOW": 73_013, "MEDIUM": 13_781, "HIGH": 158, "CRITICAL": 24}
TOP_STATE = ("Punjab", 78)          # top of top_states_by_risk
ALERTS_TOTAL = 182                   # 158 HIGH + 24 CRITICAL
ALERT_TIER_COUNTS = {"CRITICAL": 24, "HIGH": 158}
TOP_SIGNAL = ("Cost", 180)           # most-common signal in the alerts queue
COMPLETED_WORKS = 128
REPAIR_RENOVATION_TOTAL = 1_344      # category "Repair and Renovation"

# Worked example: MP (docs/frontend_card_reference.md + Session 8 verification)
MP_NAME = "Shri Harbhajan Singh (2022-28)"
MP_WORKS = 120
MP_TIERS = {"critical": 6, "high": 0, "medium": 31, "low": 83}
MP_AVG_RISK = 24.58
MP_HIGHEST_RISK = 89.84
MP_UTIL_PCT = 45.73

# Worked example: project 80673 (investigation centerpiece)
PID_SEARCH = "80673"
PRIORITY_80673 = 87.86
URGENCY_80673 = "TIER_1_IMMEDIATE_ACTION"
VENDOR_80673 = "FAUJI IRON AND CEMENT STORE"
VENDOR_RISK_80673 = 35.56
VENDOR_LEVEL_80673 = "MEDIUM"

# Frontend demo routes (Session 16 sweep: 10/10 — /home-v1 deleted, D-026 leak closed)
FRONTEND_ROUTES = [
    "/",
    "/login?role=mospi",
    "/login?role=mp",
    "/login?role=sno",
    "/login?role=dm",
    "/dashboard?role=mospi",
    "/dashboard?role=mp",
    "/dashboard?role=sno",
    "/dashboard?role=dm",
    # the investigation route is appended dynamically (needs an encoded composite ID)
]

RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if detail:
        line += f"  -- {detail}"
    print(line)


def approx(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - b) <= tol


# --- Backend boot -------------------------------------------------------------


def free_port(start: int = 8023) -> int:
    for port in range(start, start + 10):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("no free port in range")


def boot_backend() -> tuple[str, subprocess.Popen, Path]:
    """Start uvicorn on a scratch port; wait until /api/health answers loaded."""
    port = free_port()
    log_file = tempfile.NamedTemporaryFile(
        "w+", suffix="_parakh_smoke_backend.log", delete=False, encoding="utf-8"
    )
    cmd = [
        sys.executable, "-m", "uvicorn",
        "backend.app.main:app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--log-level", "info",
    ]
    proc = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=log_file, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    print(f"Booting backend: {base}  (log: {log_file.name})")

    deadline = time.time() + 180  # data load takes ~30-60 s
    while time.time() < deadline:
        if proc.poll() is not None:
            print("ERROR: backend process exited during startup. Log tail:")
            print(_tail(log_file))
            if "No module named uvicorn" in _tail(log_file):
                print("Hint: uvicorn is missing from this environment. Activate the venv:")
                print("    source venv/Scripts/activate")
            sys.exit(1)
        try:
            r = httpx.get(f"{base}/api/health", timeout=5)
            if r.status_code == 200:
                body = r.json()
                if body.get("loaded"):
                    print(f"Backend up. risk_results rows: {body.get('risk_results_rows'):,}")
                    print(_loader_source(log_file))
                    return base, proc, Path(log_file.name)
        except Exception:
            pass
        time.sleep(1.5)

    print("ERROR: backend did not become healthy within 180 s. Log tail:")
    print(_tail(log_file))
    proc.terminate()
    sys.exit(1)


def _tail(log_file, lines: int = 25) -> str:
    log_file.flush()
    text = Path(log_file.name).read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def _loader_source(log_file) -> str:
    """Report which risk-results file the loader picked (plain CSV vs .csv.gz)."""
    text = Path(log_file.name).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if "Loaded risk_results" in line and "from" in line:
            source = line.split("from")[-1].strip().rstrip(")")
            if source.endswith(".csv.gz"):
                return f"Risk table loaded from committed {source} (fresh-clone path, D-027)."
            return f"Risk table loaded from locally regenerated {source} (not the committed .gz)."
    return "Loader source line not found in backend log."


# --- Backend checks -----------------------------------------------------------


def run_backend_checks(base: str) -> dict:
    """Run all backend assertions. Returns context (worked-example IDs) for frontend checks."""
    ctx: dict = {}
    client = httpx.Client(base_url=base, timeout=60)

    def run(name: str, fn) -> None:
        try:
            detail = fn() or ""
            record(name, True, detail)
        except AssertionError as e:
            record(name, False, str(e))
        except Exception as e:
            record(name, False, f"{type(e).__name__}: {e}")

    def get_ok(path: str, **params) -> dict:
        r = client.get(path, params=params or None)
        assert r.status_code == 200, f"HTTP {r.status_code} on {path}"
        return r.json()

    # -- health ---------------------------------------------------------------
    def c_health():
        body = get_ok("/api/health")
        assert body["status"] == "ok", f"status={body['status']}"
        assert body["loaded"] is True, "data not loaded"
        assert body["risk_results_rows"] == TOTAL_WORKS, (
            f"rows={body['risk_results_rows']:,} != {TOTAL_WORKS:,}"
        )
        return f"{body['risk_results_rows']:,} rows"

    # -- dashboard summary ----------------------------------------------------
    def c_summary():
        body = get_ok("/api/dashboard/summary")
        assert body["total_works"] == TOTAL_WORKS, f"total_works={body['total_works']:,}"
        assert body["total_mps"] == TOTAL_MPS, f"total_mps={body['total_mps']} != {TOTAL_MPS}"
        got = {k: body["tier_distribution"].get(k) for k in TIER_DIST}
        assert got == TIER_DIST, f"tier_distribution={body['tier_distribution']}"
        states = body["top_states_by_risk"]
        assert states, "top_states_by_risk empty"
        top = states[0]
        assert top["state"].lower() == TOP_STATE[0].lower(), f"top state={top['state']}"
        assert top["count"] == TOP_STATE[1], f"Punjab flagged={top['count']} != {TOP_STATE[1]}"
        assert body["top_mps_by_flagged"], "top_mps_by_flagged empty"
        return (
            f"works {body['total_works']:,} / MPs {body['total_mps']} / "
            f"tiers {got['LOW']:,}-{got['MEDIUM']:,}-{got['HIGH']}-{got['CRITICAL']}"
        )

    # -- projects list + filters ----------------------------------------------
    def c_projects_list():
        body = get_ok("/api/projects", page=1, page_size=1)
        assert body["total"] == TOTAL_WORKS, f"total={body['total']:,}"
        return f"total {body['total']:,}"

    def c_projects_critical():
        body = get_ok("/api/projects", tier="CRITICAL", page_size=1)
        assert body["total"] == TIER_DIST["CRITICAL"], f"total={body['total']}"
        return f"CRITICAL total {body['total']}"

    def c_projects_completed():
        body = get_ok("/api/projects", status="completed", page_size=1)
        assert body["total"] == COMPLETED_WORKS, f"total={body['total']} != {COMPLETED_WORKS}"
        return f"completed {body['total']}"

    def c_projects_category():
        body = get_ok("/api/projects", category="Repair and Renovation", page_size=1)
        assert body["total"] == REPAIR_RENOVATION_TOTAL, (
            f"total={body['total']} != {REPAIR_RENOVATION_TOTAL}"
        )
        return f"Repair and Renovation {body['total']}"

    def c_projects_search():
        body = get_ok("/api/projects", q="school", page_size=1)
        assert body["total"] >= 1, "search 'school' returned 0 hits"
        return f"'school' hits {body['total']:,}"

    # -- worked example: project 80673 ----------------------------------------
    def c_detail_80673():
        lst = get_ok("/api/projects", q=PID_SEARCH, page_size=5)
        assert lst["total"] >= 1, f"no project matches q={PID_SEARCH}"
        pid = next(
            (i["project_id"] for i in lst["items"] if i["project_id"].split("|")[0] == PID_SEARCH),
            None,
        )
        assert pid is not None, f"project_id starting with {PID_SEARCH} not in items"
        detail = get_ok("/api/projects/" + urllib.parse.quote(pid, safe=""))
        assert detail["project_id"] == pid, "detail project_id mismatch"
        assert len(detail["engines"]) == 6, f"engines={len(detail['engines'])}"
        assert detail["investigation_urgency"] == URGENCY_80673, (
            f"urgency={detail['investigation_urgency']}"
        )
        assert detail["investigation_priority"] is not None, "priority missing"
        assert approx(detail["investigation_priority"], PRIORITY_80673), (
            f"priority={detail['investigation_priority']} != {PRIORITY_80673}"
        )
        assert detail["audit_dispatch_recommended"] is True, "audit_dispatch not recommended"
        assert detail["audit_explanation"], "audit_explanation empty"
        assert detail["evidence_payload"], "evidence_payload empty"
        vendor = (detail.get("primary_vendor") or "").upper()
        assert VENDOR_80673 in vendor, f"primary_vendor={detail.get('primary_vendor')!r}"
        assert approx(detail["vendor_risk_score"], VENDOR_RISK_80673), (
            f"vendor_risk_score={detail['vendor_risk_score']}"
        )
        assert detail["vendor_risk_level"] == VENDOR_LEVEL_80673, (
            f"vendor_risk_level={detail['vendor_risk_level']}"
        )
        ctx["pid_encoded"] = urllib.parse.quote(pid, safe="")
        return f"priority {detail['investigation_priority']} / {URGENCY_80673} / 6 engines"

    # -- worked example: MP Harbhajan Singh -----------------------------------
    def c_mp_example():
        body = get_ok("/api/mps/" + urllib.parse.quote(MP_NAME, safe=""))
        mp = body["mp"]
        assert mp["mp_name"] == MP_NAME, f"mp_name={mp['mp_name']!r}"
        assert body["total_works"] == MP_WORKS, f"total_works={body['total_works']}"
        assert body["critical_works"] == MP_TIERS["critical"], "critical_works mismatch"
        assert body["high_risk_works"] == MP_TIERS["high"], "high_risk_works mismatch"
        assert body["medium_risk_works"] == MP_TIERS["medium"], "medium_risk_works mismatch"
        assert body["low_risk_works"] == MP_TIERS["low"], "low_risk_works mismatch"
        assert approx(body["average_risk_score"], MP_AVG_RISK), (
            f"avg={body['average_risk_score']}"
        )
        assert approx(body["highest_work_risk"], MP_HIGHEST_RISK), (
            f"highest={body['highest_work_risk']}"
        )
        assert mp["utilization_pct"] is not None and approx(mp["utilization_pct"], MP_UTIL_PCT), (
            f"util={mp['utilization_pct']}"
        )
        return f"{MP_WORKS} works / tiers 6-0-31-83 / avg {body['average_risk_score']}"

    # -- MPs roster -------------------------------------------------------------
    def c_mps_roster():
        body = get_ok("/api/mps", page_size=1)
        assert body["total"] == TOTAL_MPS, f"total={body['total']} != {TOTAL_MPS}"
        return f"{body['total']} MPs"

    # -- alerts ------------------------------------------------------------------
    def c_alerts():
        body = get_ok("/api/alerts", page_size=1)
        assert body["total"] == ALERTS_TOTAL, f"total={body['total']} != {ALERTS_TOTAL}"
        got = {k: body["tier_counts"].get(k) for k in ALERT_TIER_COUNTS}
        assert got == ALERT_TIER_COUNTS, f"tier_counts={body['tier_counts']}"
        sigs = body["signal_aggregates"]
        assert sigs, "signal_aggregates empty"
        top = (sigs[0]["signal"], sigs[0]["count"])
        assert top == TOP_SIGNAL, f"top signal={top} != {TOP_SIGNAL}"
        return f"total {ALERTS_TOTAL} / CRITICAL {got['CRITICAL']} + HIGH {got['HIGH']} / top {top[0]} {top[1]}"

    # -- agencies ------------------------------------------------------------------
    def c_agencies():
        body = get_ok("/api/agencies", page_size=1)
        assert body["total"] > 0, "no agencies"
        item = body["items"][0]
        for field in ("agency_id", "agency_risk_score", "agency_risk_level"):
            assert field in item, f"missing field {field}"
        return f"{body['total']} agencies"

    print("\nBackend checks:", base)
    run("health: data loaded, frozen row count", c_health)
    run("dashboard summary: works / MPs / tier distribution / top state", c_summary)
    run("projects list: frozen total", c_projects_list)
    run("projects filter: CRITICAL count", c_projects_critical)
    run("projects filter: completed count", c_projects_completed)
    run("projects filter: Repair and Renovation count", c_projects_category)
    run("projects search: 'school' hits", c_projects_search)
    run("worked example 80673: priority / urgency / engines / evidence / vendor", c_detail_80673)
    run(f"worked example MP: {MP_NAME}", c_mp_example)
    run("MPs roster: frozen count", c_mps_roster)
    run("alerts: frozen totals + tier counts + top signal", c_alerts)
    run("agencies: list + fields", c_agencies)
    return ctx


# --- Frontend checks ----------------------------------------------------------


def run_frontend_checks(base: str, ctx: dict) -> None:
    """Probe the running Next.js dev server for HTTP 200 on every demo route."""
    client = httpx.Client(timeout=120, follow_redirects=True)  # dev-server cold compiles are slow

    routes = list(FRONTEND_ROUTES)
    if ctx.get("pid_encoded"):
        routes.append(f"/investigation/{ctx['pid_encoded']}")
    else:
        record("frontend routes: investigation page", False, "no composite project id captured from backend checks")

    print(f"\nFrontend checks: {base}  ({len(routes)} demo routes)")
    for route in routes:
        name = f"GET {route}"
        try:
            r = client.get(base + route)
            ok = r.status_code == 200 and len(r.content) > 0
            record(name, ok, "" if ok else f"HTTP {r.status_code}, {len(r.content)} bytes")
        except Exception as e:
            record(name, False, f"{type(e).__name__}: {e}")
    print(
        "\nNote: route 200s prove the pages serve; dashboard KPI numbers are "
        "client-side fetches -- open the browser once per TEST-CHECKLIST.md."
    )


# --- Summary / teardown ---------------------------------------------------------


def summarize() -> int:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print("\n" + "=" * 66)
    print(f"SMOKE RESULT: {passed}/{len(RESULTS)} checks passed")
    if failed:
        print("Failed checks:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  - {name}" + (f"  -- {detail}" if detail else ""))
        print("\nNOT demo-ready. Fix the failures above, then re-run.")
        return 1
    print("DEMO-READY: frozen numbers + routes all verified on this machine.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="PARAKH E2E smoke check (demo readiness).")
    ap.add_argument("--backend-url", help="check an already-running backend instead of booting one")
    ap.add_argument("--frontend", action="store_true", help="also probe the Next.js dev server")
    ap.add_argument("--frontend-url", default="http://localhost:3000", help="dev server base URL (default: http://localhost:3000)")
    args = ap.parse_args()

    proc = None
    log_path = None
    try:
        if args.backend_url:
            base = args.backend_url.rstrip("/")
            print(f"Using already-running backend: {base}")
        else:
            base, proc, log_path = boot_backend()

        ctx = run_backend_checks(base)

        if args.frontend or args.frontend_url != "http://localhost:3000":
            run_frontend_checks(args.frontend_url.rstrip("/"), ctx)
        else:
            print("\n(Frontend probes skipped -- run with --frontend while `npm run dev` is up.)")

        return summarize()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            print(f"\nBackend stopped. Boot log kept at: {log_path}")


if __name__ == "__main__":
    sys.exit(main())
