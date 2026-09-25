"""
citizen.py
==========
Citizen Participation Portal backend (D-032) — the public, demo-grade
counterpart to the authority dashboards.

Endpoints (all under /api/citizen, mounted in main.py):
- POST /api/citizen/login                  — demo Aadhaar + OTP (simulated, labeled)
- GET  /api/citizen/me                     — the logged-in citizen's activity summary
- POST /api/citizen/vote                   — upvote/unupvote a work (toggle;
                                             UNIQUE(citizen, work) enforced by SQLite)
- GET  /api/citizen/feed                   — works + public upvote counts, filter/sort/search
- POST /api/citizen/reports                — file a citizen report (criteria + comment +
                                             optional image + optional location)
- GET  /api/citizen/reports                — recent citizen reports (public, demo-labeled)
- GET  /api/citizen/psi/{project_id}       — Public Satisfaction Indicator for one work
- GET  /api/citizen/overview               — portal participation stats

Storage: SQLite at backend/citizen.db (stdlib sqlite3 — no new deps; the frozen
CSV layer D-001 is untouched). Gitignored runtime state; tests redirect it with
the PARAKH_CITIZEN_DB env var (read lazily per connection). Uploaded images go
to backend/uploads/ (gitignored).

Honesty (D-008/D-032, non-negotiable):
- Login is a SIMULATED demo Aadhaar+OTP flow — no real UIDAI integration.
- Seed interactions are SYNTHETIC, deterministically generated (every laptop
  serves identical numbers — D-027 spirit), and flagged `is_seed`/`demo_seed`.
- Votes: the one-vote-per-citizen RULE is genuinely enforced server-side; only
  the identity is demo.
- Images/coordinates are citizen-submitted and UNVERIFIED by definition — the
  API never claims otherwise, and a coarse location sanity check only downgrades
  wording (NEVER promotes anything to "verified").
- The PSI is a participation/sentiment signal — explicitly NOT a detection
  engine and never merged into the risk score.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..data_loader import data_store
from ..schemas import (
    CitizenFacetsResponse,
    CitizenFacetState,
    CitizenFeedItem,
    CitizenFeedResponse,
    CitizenLoginRequest,
    CitizenLoginResponse,
    CitizenMe,
    CitizenOverviewResponse,
    CitizenPsiResponse,
    CitizenReportItem,
    CitizenReportListResponse,
    CitizenVoteRequest,
    CitizenVoteResponse,
)

router = APIRouter()

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB_PATH = _BACKEND_ROOT / "citizen.db"
_DEFAULT_UPLOAD_DIR = _BACKEND_ROOT / "uploads"

# Criteria vocabulary for citizen reports (fixed set — keeps the UI and the
# feed aggregation stable). "other" carries free text via the comment field.
REPORT_CRITERIA = ("stalled", "quality", "cost", "ghost", "other")

# Demo image upload cap: 5 MB, common raster formats.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
_ALLOWED_IMAGE_EXT = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}


def _db_path() -> Path:
    env = os.environ.get("PARAKH_CITIZEN_DB")
    return Path(env) if env else _DEFAULT_DB_PATH


def _upload_dir() -> Path:
    env = os.environ.get("PARAKH_UPLOAD_DIR")
    d = Path(env) if env else _DEFAULT_UPLOAD_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


_DB_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS citizens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aadhaar_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER NOT NULL REFERENCES citizens(id),
            project_id TEXT NOT NULL,
            reasons TEXT,
            is_seed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(citizen_id, project_id)
        );
        CREATE TABLE IF NOT EXISTS citizen_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            citizen_id INTEGER REFERENCES citizens(id),
            project_id TEXT NOT NULL,
            criteria TEXT NOT NULL,
            comment TEXT,
            image_path TEXT,
            latitude REAL,
            longitude REAL,
            location_sanity TEXT,
            satisfaction INTEGER,
            verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            is_seed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_votes_project ON votes(project_id);
        CREATE INDEX IF NOT EXISTS idx_reports_project ON citizen_reports(project_id);
        """
    )
    # Self-healing migration for pre-reason dbs (same pattern as reports.db):
    # votes.reasons lands on existing files without a wipe. CREATE TABLE above
    # already includes the column for fresh dbs.
    try:
        conn.execute("ALTER TABLE votes ADD COLUMN reasons TEXT")
    except sqlite3.OperationalError:
        pass  # column exists
    try:
        conn.execute("ALTER TABLE citizen_reports ADD COLUMN satisfaction INTEGER")
    except sqlite3.OperationalError:
        pass  # column exists
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_aadhaar(aadhaar: str) -> str:
    """One-way hash of the demo ID — we never store the raw number."""
    return hashlib.sha256(f"parakh-demo:{aadhaar.strip()}".encode()).hexdigest()


def _mask_from_hash(h: str) -> str:
    """Masked display id derived from the stored hash — used consistently by
    /login and /me so both screens show the same citizen id."""
    return f"CIT-XXXX XXXX {h[-4:]}"


def _lookup_project(project_id: str) -> pd.Series:
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")
    matches = df.loc[df["project_id"].astype(str) == project_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return matches.iloc[0]


def _require_token(token: str) -> int:
    """token → citizens.id (401 when unknown)."""
    if not token or not token.startswith("demo-citizen-"):
        raise HTTPException(status_code=401, detail="Invalid or missing citizen token (log in first)")
    h = _hash_aadhaar(token[len("demo-citizen-"):])
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            row = conn.execute(
                "SELECT id FROM citizens WHERE aadhaar_hash = ?", (h,)
            ).fetchone()
        finally:
            conn.close()
    if row is None:
        raise HTTPException(status_code=401, detail="Unknown citizen token (log in first)")
    return int(row["id"])


# ─── Seed (deterministic synthetic participation, D-027 spirit) ──────────────


def _seed_if_empty(conn: sqlite3.Connection) -> bool:
    """Seed synthetic demo participation exactly once (per db file).

    Deterministic: a fixed RNG seed + fixed citizen pool + risk-data-derived
    work selection → every laptop serves identical numbers. All seed rows are
    flagged is_seed=1 so the UI can label them synthetic.
    """
    already = conn.execute(
        "SELECT COUNT(*) FROM citizens WHERE aadhaar_hash LIKE 'seed:%'"
    ).fetchone()[0]
    if already:
        return False

    rng = random.Random(20260923)  # deterministic — date-stamped seed
    now = _now_iso()

    # Pick seed works from the frozen risk data: top-flagged works first, so
    # the feed visibly lines up with the risk story (citizen attention
    # clustering around the same works the engines flag is the demo beat).
    df = data_store.risk_results
    if df is None or df.empty:
        return False  # no data yet — nothing to seed against

    top = df.sort_values("overall_risk_score", ascending=False).head(60)
    seed_works = [str(p) for p in top["project_id"].tolist()]
    if not seed_works:
        return False

    # Fixed synthetic citizen pool (hashed demo IDs — never real numbers).
    citizen_ids: list[int] = []
    for i in range(42):
        h = f"seed:citizen-{i:03d}"
        cur = conn.execute(
            "INSERT INTO citizens (aadhaar_hash, created_at) VALUES (?, ?)",
            (h, now),
        )
        citizen_ids.append(int(cur.lastrowid))

    # Votes: 140 synthetic upvotes concentrated on the top 25 works, each
    # with deterministic concern reasons (drives the PSI reasons breakdown).
    vote_reason_pool = [
        ["stalled"],
        ["stalled", "quality"],
        ["quality"],
        ["cost"],
        ["ghost"],
    ]
    for i in range(140):
        work = seed_works[rng.randrange(min(25, len(seed_works)))]
        cit = citizen_ids[rng.randrange(len(citizen_ids))]
        reasons = json.dumps(vote_reason_pool[i % len(vote_reason_pool)])
        try:
            conn.execute(
                "INSERT INTO votes (citizen_id, project_id, reasons, is_seed, created_at) VALUES (?, ?, ?, 1, ?)",
                (cit, work, reasons, now),
            )
        except sqlite3.IntegrityError:
            pass  # UNIQUE(citizen, work) — same as a real double-vote

    # Citizen reports: 30 synthetic reports on the top 40 works.
    criteria_pool = [
        ["stalled"],
        ["stalled", "quality"],
        ["quality"],
        ["cost"],
        ["ghost"],
        ["stalled", "cost"],
    ]
    comments = [
        "Work shown as ongoing for over a year, no visible progress at site.",
        "Material quality looks poor; photos from the area show cracks already.",
        "Local sources claim the estimated cost is much higher than market rate.",
        "No sign of this work having started despite being sanctioned.",
        "Contractor presence stopped months ago; site is abandoned.",
        "Billed amount seems inconsistent with the work done so far.",
    ]
    for i in range(30):
        work = seed_works[rng.randrange(min(40, len(seed_works)))]
        cit = citizen_ids[rng.randrange(len(citizen_ids))]
        crit = json.dumps(criteria_pool[i % len(criteria_pool)])
        comment = comments[i % len(comments)] if i % 3 != 2 else None
        satisfaction = rng.choice([1, 2, 2, 3, 3, 4])  # skewed negative — demo story
        # Synthetic coords: roughly inside India's bounding box, deterministic.
        lat = round(rng.uniform(8.5, 28.0), 5)
        lon = round(rng.uniform(69.0, 87.0), 5)
        conn.execute(
            "INSERT INTO citizen_reports (citizen_id, project_id, criteria, comment, latitude, longitude, location_sanity, satisfaction, verification_status, is_seed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'NO_REFERENCE', ?, 'UNVERIFIED', 1, ?)",
            (cit, work, crit, comment, lat, lon, satisfaction, now),
        )

    conn.commit()
    return True


def _ensure_seeded() -> None:
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            _seed_if_empty(conn)
        finally:
            conn.close()


# ─── Location sanity (coarse, wording-only — never promotes to verified) ─────

# Very coarse bounding boxes (lat_min, lat_max, lon_min, lon_max) for the
# sanity check's wording. Deliberately generous — this is a demo-grade
# plausibility signal, NOT verification (D-032).
_STATE_BBOXES: dict[str, tuple[float, float, float, float]] = {
    "punjab": (29.5, 32.6, 73.8, 76.9),
    "haryana": (27.6, 30.9, 74.4, 77.6),
    "rajasthan": (23.0, 30.2, 69.4, 78.3),
    "uttar pradesh": (23.8, 30.4, 77.0, 84.7),
    "bihar": (24.3, 27.5, 83.3, 88.3),
    "maharashtra": (15.6, 22.1, 72.6, 80.9),
    "gujarat": (20.1, 24.7, 68.1, 74.5),
    "madhya pradesh": (21.0, 26.9, 74.0, 82.8),
    "karnataka": (11.6, 18.5, 74.0, 78.6),
    "kerala": (8.2, 12.8, 74.8, 77.4),
    "tamil nadu": (8.0, 13.6, 76.2, 80.4),
    "andhra pradesh": (12.6, 19.9, 76.7, 84.8),
    "telangana": (15.8, 19.9, 77.2, 81.8),
    "odisha": (17.7, 22.6, 81.3, 87.6),
    "west bengal": (21.4, 27.2, 85.8, 89.9),
    "assam": (24.0, 28.0, 89.6, 96.1),
    "jharkhand": (21.9, 25.3, 83.3, 87.9),
    "chhattisgarh": (17.7, 24.1, 80.2, 84.4),
    "uttarakhand": (28.7, 31.5, 77.3, 81.1),
    "himachal pradesh": (30.3, 33.3, 75.5, 79.0),
}


def _location_sanity(lat: Optional[float], lon: Optional[float], claimed_state: str) -> str:
    """Coarse plausibility wording for citizen-submitted coordinates.

    - PLAUSIBLE: inside the claimed state's generous bounding box.
    - FAR_FROM_CLAIMED_STATE: coordinates outside it (spam signal — wording
      only; the report stays UNVERIFIED either way).
    - NO_REFERENCE: state unknown → nothing to check against.
    """
    if lat is None or lon is None:
        return "NO_LOCATION"
    state = (claimed_state or "").strip().lower()
    if not state or state not in _STATE_BBOXES:
        return "NO_REFERENCE"
    lat_min, lat_max, lon_min, lon_max = _STATE_BBOXES[state]
    if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
        return "PLAUSIBLE"
    return "FAR_FROM_CLAIMED_STATE"


# ─── Feed helpers ─────────────────────────────────────────────────────────────


def _vote_counts(project_ids: Optional[list[str]] = None) -> dict[str, int]:
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            if project_ids:
                qmarks = ",".join("?" * len(project_ids))
                rows = conn.execute(
                    f"SELECT project_id, COUNT(*) c FROM votes WHERE project_id IN ({qmarks}) GROUP BY project_id",
                    project_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT project_id, COUNT(*) c FROM votes GROUP BY project_id"
                ).fetchall()
        finally:
            conn.close()
    return {str(r["project_id"]): int(r["c"]) for r in rows}


def _report_counts(project_ids: Optional[list[str]] = None) -> dict[str, int]:
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            if project_ids:
                qmarks = ",".join("?" * len(project_ids))
                rows = conn.execute(
                    f"SELECT project_id, COUNT(*) c FROM citizen_reports WHERE project_id IN ({qmarks}) GROUP BY project_id",
                    project_ids,
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT project_id, COUNT(*) c FROM citizen_reports GROUP BY project_id"
                ).fetchall()
        finally:
            conn.close()
    return {str(r["project_id"]): int(r["c"]) for r in rows}


def _my_votes(citizen_id: int, project_ids: list[str]) -> set[str]:
    if not project_ids:
        return set()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            qmarks = ",".join("?" * len(project_ids))
            rows = conn.execute(
                f"SELECT project_id FROM votes WHERE citizen_id = ? AND project_id IN ({qmarks})",
                [citizen_id] + project_ids,
            ).fetchall()
        finally:
            conn.close()
    return {str(r["project_id"]) for r in rows}


def _concern_breakdown(project_ids: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    """Combined per-reason concern counts per work — the shared citizen signal.

    An upvote-with-reason and a report-criteria are the SAME signal in PARAKH
    (D-032): both use the same vocabulary, so per work each reason tallies
    `reports + upvotes`. The split is preserved so the UI can stay honest:
    reports are evidence-bearing submissions, upvotes are echoes of the same
    concern. Returns {project_id: {reason: {total, reports, upvotes}}}.
    """
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            combined: dict[str, dict[str, dict[str, int]]] = {}
            for table, col, source in (
                ("votes", "reasons", "upvotes"),
                ("citizen_reports", "criteria", "reports"),
            ):
                for (pid, raw) in conn.execute(
                    f"SELECT project_id, {col} FROM {table} WHERE {col} IS NOT NULL"
                ):
                    try:
                        tags = json.loads(str(raw))
                    except json.JSONDecodeError:
                        continue
                    bucket = combined.setdefault(str(pid), {})
                    for tag in tags:
                        tag = str(tag)
                        if tag in REPORT_CRITERIA:
                            entry = bucket.setdefault(
                                tag, {"total": 0, "reports": 0, "upvotes": 0}
                            )
                            entry["total"] += 1
                            entry[source] += 1
        finally:
            conn.close()
    if project_ids:
        keep = set(project_ids)
        combined = {k: v for k, v in combined.items() if k in keep}
    return combined


def _satisfaction_stats() -> dict[str, tuple[float, int]]:
    """Per-work mean of citizens' 1–5 satisfaction ratings (from reports).
    Returns {project_id: (avg_rounded_1dp, rating_count)}."""
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            rows = conn.execute(
                "SELECT project_id, AVG(satisfaction) a, COUNT(*) c "
                "FROM citizen_reports WHERE satisfaction IS NOT NULL GROUP BY project_id"
            ).fetchall()
        finally:
            conn.close()
    return {str(r["project_id"]): (round(float(r["a"]), 1), int(r["c"])) for r in rows}


def _feed_item(
    row: pd.Series,
    votes: int,
    reports: int,
    voted: Optional[bool],
    top_concerns: Optional[list[dict]] = None,
    satisfaction: Optional[tuple[float, int]] = None,
) -> CitizenFeedItem:
    wd = row.get("work_description")
    status = row.get("status")
    return CitizenFeedItem(
        project_id=str(row["project_id"]),
        work_description=str(wd) if wd is not None and pd.notna(wd) else None,
        mp_name=str(row["mp_name"]),
        state=str(row["state"]),
        constituency=str(row["constituency"]),
        category=str(row.get("category", "")) if pd.notna(row.get("category", "")) else "",
        status=str(status) if status is not None and pd.notna(status) else None,
        risk_category=str(row["risk_category"]),
        risk_score_display=round(float(row["overall_risk_score"]) * 100),
        recommended_amount=float(row.get("recommended_amount", 0) or 0),
        upvote_count=votes,
        report_count=reports,
        top_concerns=top_concerns or [],
        satisfaction_avg=satisfaction[0] if satisfaction else None,
        satisfaction_count=satisfaction[1] if satisfaction else 0,
        voted=voted,
    )


def _report_row_to_item(row: sqlite3.Row, enrich: Optional[pd.Series]) -> CitizenReportItem:
    try:
        criteria = json.loads(str(row["criteria"]))
    except (json.JSONDecodeError, TypeError):
        criteria = [str(row["criteria"])]

    if enrich is not None:
        wd = enrich.get("work_description")
        mp_name = str(enrich.get("mp_name", "") or "")
        state = str(enrich.get("state", "") or "")
        category = str(enrich.get("risk_category", "") or "")
        score = round(float(enrich.get("overall_risk_score", 0) or 0) * 100)
    else:
        wd, mp_name, state, category, score = None, "", "", "", 0

    image_path = row["image_path"] if "image_path" in row.keys() else None
    is_seed = bool(row["is_seed"]) if "is_seed" in row.keys() else False

    satisfaction = row["satisfaction"] if "satisfaction" in row.keys() else None

    return CitizenReportItem(
        id=int(row["id"]),
        project_id=str(row["project_id"]),
        masked_id=_mask_from_seed_row(str(row["citizen_id"])) if not is_seed else "CIT-SEED (synthetic)",
        criteria=criteria,
        satisfaction=int(satisfaction) if satisfaction is not None else None,
        comment=str(row["comment"]) if row["comment"] else None,
        has_image=bool(image_path),
        image_url=f"/api/citizen/uploads/{Path(str(image_path)).name}" if image_path else None,
        latitude=float(row["latitude"]) if row["latitude"] is not None else None,
        longitude=float(row["longitude"]) if row["longitude"] is not None else None,
        location_sanity=str(row["location_sanity"]) if row["location_sanity"] else None,
        verification_status=str(row["verification_status"]),
        is_seed=is_seed,
        created_at=str(row["created_at"]),
        work_description=str(wd) if wd is not None and pd.notna(wd) else None,
        mp_name=mp_name,
        state=state,
        risk_category=category,
        risk_score_display=score,
    )


def _mask_from_seed_row(citizen_id: str) -> str:
    """Deterministic masked display id derived from the stored hash."""
    return "CIT-" + hashlib.sha256(citizen_id.encode()).hexdigest()[:4].upper()


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/login", response_model=CitizenLoginResponse)
def citizen_login(payload: CitizenLoginRequest):
    """Demo Aadhaar + OTP login (simulated, labeled — D-032).

    Any 12-digit ID + any 6-digit OTP is accepted. The token embeds the raw
    demo ID (demo-only transport; the db stores only a one-way hash).
    """
    aadhaar = payload.aadhaar.strip()
    if not aadhaar.isdigit():
        raise HTTPException(status_code=422, detail="Aadhaar must be 12 digits")
    h = _hash_aadhaar(aadhaar)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            existing = conn.execute(
                "SELECT id FROM citizens WHERE aadhaar_hash = ?", (h,)
            ).fetchone()
            is_new = existing is None
            if is_new:
                conn.execute(
                    "INSERT INTO citizens (aadhaar_hash, created_at) VALUES (?, ?)",
                    (h, _now_iso()),
                )
                conn.commit()
        finally:
            conn.close()

    return CitizenLoginResponse(
        token=f"demo-citizen-{aadhaar}",
        masked_id=_mask_from_hash(h),
        is_new=is_new,
        demo_notice="Demo login: Aadhaar + OTP verification is simulated for this prototype — production would integrate with UIDAI.",
    )


@router.get("/me", response_model=CitizenMe)
def citizen_me(token: str = Query(...)):
    citizen_id = _require_token(token)
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            cit = conn.execute(
                "SELECT aadhaar_hash, created_at FROM citizens WHERE id = ?", (citizen_id,)
            ).fetchone()
            upvotes = conn.execute(
                "SELECT COUNT(*) c FROM votes WHERE citizen_id = ?", (citizen_id,)
            ).fetchone()[0]
            reports = conn.execute(
                "SELECT COUNT(*) c FROM citizen_reports WHERE citizen_id = ?", (citizen_id,)
            ).fetchone()[0]
        finally:
            conn.close()
    h = str(cit["aadhaar_hash"])
    return CitizenMe(
        masked_id=_mask_from_hash(h),
        created_at=str(cit["created_at"]),
        upvotes_cast=int(upvotes),
        reports_filed=int(reports),
    )


@router.post("/vote", response_model=CitizenVoteResponse)
def citizen_vote(payload: CitizenVoteRequest):
    """Upvote/unupvote a work (Reddit-style toggle). One vote per citizen per
    work — enforced by UNIQUE(citizen_id, project_id) in SQLite, so the
    anti-spam rule is real even though the identity is demo."""
    citizen_id = _require_token(payload.token)
    _lookup_project(payload.project_id)  # 404 on unknown work

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            existing = conn.execute(
                "SELECT id FROM votes WHERE citizen_id = ? AND project_id = ?",
                (citizen_id, payload.project_id),
            ).fetchone()
            if existing is not None:
                conn.execute("DELETE FROM votes WHERE id = ?", (int(existing["id"]),))
                voted = False
            else:
                reasons_json = (
                    json.dumps(payload.reasons) if payload.reasons else None
                )
                conn.execute(
                    "INSERT INTO votes (citizen_id, project_id, reasons, created_at) VALUES (?, ?, ?, ?)",
                    (citizen_id, payload.project_id, reasons_json, _now_iso()),
                )
                voted = True
            conn.commit()
            count = conn.execute(
                "SELECT COUNT(*) c FROM votes WHERE project_id = ?", (payload.project_id,)
            ).fetchone()[0]
        finally:
            conn.close()

    return CitizenVoteResponse(
        project_id=payload.project_id,
        voted=voted,
        upvote_count=int(count),
        demo_notice="Demo identity: one vote per citizen enforced server-side.",
    )


@router.get("/facets", response_model=CitizenFacetsResponse)
def citizen_facets():
    """Facet index for the feed's 'near me' filters (D-032): every state with
    its constituency + MP lists, straight from the real dataset so the
    dropdowns can never offer options the data can't honor.

    Read-only, cheap (groupby over ~87k rows once per call) and identical for
    every citizen — no token required.
    """
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    # Flagged counts computed once (same convention as /dashboard/states:
    # most-attention states lead the dropdown).
    flagged = (
        df[df["risk_category"].isin(["HIGH", "CRITICAL"])]
        .groupby("state")["project_id"]
        .count()
    )

    grouped = df.groupby("state", dropna=True)
    states: list[CitizenFacetState] = []
    total_constituencies = 0
    for state, g in grouped:
        constituencies = sorted(
            {str(c).strip() for c in g["constituency"].dropna() if str(c).strip()}
        )
        mps = sorted({str(m).strip() for m in g["mp_name"].dropna() if str(m).strip()})
        total_constituencies += len(constituencies)
        states.append(
            CitizenFacetState(
                state=str(state),
                works=int(len(g)),
                constituencies=constituencies,
                mps=mps,
            )
        )

    states.sort(
        key=lambda s: (
            -int(flagged.get(s.state, 0)),
            -s.works,
            s.state,
        )
    )
    return CitizenFacetsResponse(
        total_states=len(states),
        total_constituencies=total_constituencies,
        states=states,
    )


@router.get("/feed", response_model=CitizenFeedResponse)
def citizen_feed(
    token: Optional[str] = Query(None, description="Optional — adds per-citizen voted flags"),
    q: Optional[str] = Query(None, description="Search project id or work description"),
    tier: Optional[str] = Query(None, description="Risk tier: LOW, MEDIUM, HIGH, CRITICAL"),
    state: Optional[str] = Query(None),
    constituency: Optional[str] = Query(None),
    mp: Optional[str] = Query(None, description="MP name filter (citizen report finder)"),
    category: Optional[str] = Query(None),
    sort: str = Query("upvotes_desc", description="upvotes_desc | risk_desc | amount_desc | reports_desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """The public feed: works + how much public attention each has."""
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")
    _ensure_seeded()  # first public read on a fresh db must show the demo participation

    citizen_id: Optional[int] = None
    if token:
        citizen_id = _require_token(token)

    filtered = df.copy()
    if data_store.master_works is not None:
        mw_cols = [c for c in ("project_id", "work_description", "status") if c in data_store.master_works.columns]
        mw = data_store.master_works[mw_cols].copy()
        mw["project_id"] = mw["project_id"].astype(str)
        filtered["project_id"] = filtered["project_id"].astype(str)
        filtered = filtered.merge(mw, on="project_id", how="left")

    if tier:
        filtered = filtered[filtered["risk_category"] == tier.upper()]
    if state:
        filtered = filtered[filtered["state"].str.contains(state, case=False, na=False, regex=False)]
    if constituency:
        filtered = filtered[filtered["constituency"].str.contains(constituency, case=False, na=False, regex=False)]
    if mp:
        filtered = filtered[filtered["mp_name"].str.contains(mp, case=False, na=False, regex=False)]
    if category:
        filtered = filtered[filtered["category"].astype(str).str.contains(category, case=False, na=False, regex=False)]
    if q:
        id_match = filtered["project_id"].str.contains(q, case=False, na=False, regex=False)
        if "work_description" in filtered.columns:
            mask = id_match | filtered["work_description"].astype(str).str.contains(q, case=False, na=False, regex=False)
        else:
            mask = id_match
        filtered = filtered[mask]

    # Engagement counts for ALL filtered works — sorting must happen on the
    # dataframe BEFORE pagination, or every page shows only page-local order.
    vcounts = _vote_counts()
    rcounts = _report_counts()
    concerns = _concern_breakdown([])  # combined reasons per work (votes + reports)
    sats = _satisfaction_stats()
    filtered = filtered.copy()
    pid_str = filtered["project_id"].astype(str)
    filtered["__votes"] = pid_str.map(vcounts).fillna(0)
    filtered["__reports"] = pid_str.map(rcounts).fillna(0)
    # Combined signal volume: every reason tag on every vote + report.
    filtered["__signals"] = pid_str.map(
        {pid: sum(v["total"] for v in c.values()) for pid, c in concerns.items()}
    ).fillna(0)

    if sort == "risk_desc":
        filtered = filtered.sort_values("overall_risk_score", ascending=False, kind="stable")
    elif sort == "amount_desc":
        filtered = filtered.sort_values("recommended_amount", ascending=False, kind="stable")
    elif sort == "reports_desc":
        filtered = filtered.sort_values(["__reports", "__votes"], ascending=False, kind="stable")
    elif sort == "signals_desc":
        # The combined citizen-voice ordering: what are people actually saying?
        filtered = filtered.sort_values(["__signals", "overall_risk_score"], ascending=False, kind="stable")
    else:  # upvotes_desc (default — the Reddit-style ordering)
        filtered = filtered.sort_values(["__votes", "overall_risk_score"], ascending=False, kind="stable")

    total = len(filtered)
    pages = math.ceil(total / page_size) if total > 0 else 1
    start = (page - 1) * page_size
    page_df = filtered.iloc[start : start + page_size]

    ids = [str(p) for p in page_df["project_id"].tolist()]
    my_votes: set[str] = _my_votes(citizen_id, ids) if citizen_id else set()

    def _top_concerns(pid: str) -> list[dict]:
        """Top reasons for this work, combined count + honest split."""
        bucket = concerns.get(pid, {})
        ordered = sorted(bucket.items(), key=lambda kv: (-kv[1]["total"], kv[0]))[:3]
        return [
            {
                "reason": k,
                "count": v["total"],
                "report_count": v["reports"],
                "upvote_count": v["upvotes"],
            }
            for k, v in ordered
        ]

    items = [
        _feed_item(
            row,
            int(row["__votes"]),
            int(row["__reports"]),
            (str(row["project_id"]) in my_votes) if citizen_id else None,
            top_concerns=_top_concerns(str(row["project_id"])),
            satisfaction=sats.get(str(row["project_id"])),
        )
        for _, row in page_df.iterrows()
    ]

    return CitizenFeedResponse(
        total=total, page=page, page_size=page_size, pages=pages,
        demo_seed=True, items=items,
    )


@router.post("/reports", response_model=CitizenReportItem)
async def create_citizen_report(
    token: str = File(..., description="Citizen token from /login"),
    project_id: str = File(...),
    criteria: Optional[str] = File(None, description="Comma-separated: stalled,quality,cost,ghost,other"),
    satisfaction: Optional[int] = File(None, description="1–5 satisfaction rating (pure feedback when no criteria)") ,
    comment: Optional[str] = File(None),
    image: Optional[UploadFile] = File(None),
    latitude: Optional[float] = File(None),
    longitude: Optional[float] = File(None),
):
    """File a citizen report on a work (demo). Everything submitted is stored
    as UNVERIFIED — images/coords never become 'verified' via this API.

    Two report flavors share this endpoint: a PROBLEM report (≥1 criteria,
    satisfaction optional) and pure SATISFACTION FEEDBACK (1–5 rating, no
    criteria). At least one of the two is required."""
    citizen_id = _require_token(token)
    project_row = _lookup_project(project_id)

    crit_list = [c.strip().lower() for c in (criteria or "").split(",") if c.strip()]
    if satisfaction is not None and not 1 <= satisfaction <= 5:
        raise HTTPException(status_code=422, detail="Satisfaction must be 1–5")
    if not crit_list and satisfaction is None:
        raise HTTPException(
            status_code=422,
            detail="Select at least one criteria OR give a satisfaction rating",
        )
    unknown = [c for c in crit_list if c not in REPORT_CRITERIA]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown criteria: {', '.join(unknown)}")
    unknown = [c for c in crit_list if c not in REPORT_CRITERIA]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown criteria: {', '.join(unknown)}")
    if comment and len(comment) > 2000:
        raise HTTPException(status_code=422, detail="Comment too long (max 2000 chars)")

    # Location sanity wording (coarse, never verifies anything)
    sanity = _location_sanity(latitude, longitude, str(project_row.get("state", "") or ""))

    # Optional demo image upload
    image_path: Optional[str] = None
    if image is not None and image.filename:
        ext = _ALLOWED_IMAGE_EXT.get(Path(image.filename).suffix.lower())
        ctype = (image.content_type or "").lower()
        if ext is None or ctype not in _ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=422, detail="Image must be JPEG/PNG/WebP")
        blob = await image.read()
        if len(blob) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="Image too large (max 5 MB)")
        if not blob:
            raise HTTPException(status_code=422, detail="Empty image file")
        name = f"citizen-{secrets.token_hex(8)}{ext}"
        (_upload_dir() / name).write_bytes(blob)
        image_path = name

    now = _now_iso()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            cur = conn.execute(
                "INSERT INTO citizen_reports (citizen_id, project_id, criteria, comment, image_path, latitude, longitude, location_sanity, satisfaction, verification_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED', ?)",
                (citizen_id, project_id, json.dumps(crit_list), comment, image_path, latitude, longitude, sanity, satisfaction, now),
            )
            report_id = int(cur.lastrowid)
            conn.commit()
            row = conn.execute("SELECT * FROM citizen_reports WHERE id = ?", (report_id,)).fetchone()
        finally:
            conn.close()

    return _report_row_to_item(row, project_row)


@router.get("/reports", response_model=CitizenReportListResponse)
def list_citizen_reports(
    project_id: Optional[str] = Query(None, description="Filter to one work"),
    limit: int = Query(50, ge=1, le=200),
):
    """Recent citizen reports (public, demo-labeled)."""
    _ensure_seeded()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM citizen_reports WHERE project_id = ? ORDER BY id DESC LIMIT ?",
                    (project_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM citizen_reports ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        finally:
            conn.close()

    df = data_store.risk_results
    emap: dict[str, pd.Series] = {}
    if df is not None and not df.empty:
        ids = list({str(r["project_id"]) for r in rows})
        if ids:
            sub = df[df["project_id"].astype(str).isin(ids)].drop_duplicates(subset=["project_id"])
            if "work_description" not in sub.columns and data_store.master_works is not None:
                mw_cols = [c for c in ("project_id", "work_description") if c in data_store.master_works.columns]
                sub = sub.merge(data_store.master_works[mw_cols], on="project_id", how="left")
            emap = {str(r["project_id"]): r for _, r in sub.iterrows()}

    return CitizenReportListResponse(
        total=len(rows),
        demo_seed=True,
        items=[_report_row_to_item(r, emap.get(str(r["project_id"]))) for r in rows],
    )


@router.get("/psi/{project_id}", response_model=CitizenPsiResponse)
def citizen_psi(project_id: str):
    """Public Satisfaction Indicator for one work — a participation signal,
    NOT a detection engine and NOT part of the risk score."""
    project_row = _lookup_project(project_id)
    _ensure_seeded()
    upvotes = _vote_counts([project_id]).get(project_id, 0)
    reports = _report_counts([project_id]).get(project_id, 0)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            distinct = conn.execute(
                "SELECT COUNT(*) c FROM (SELECT citizen_id FROM votes WHERE project_id = ? "
                "UNION SELECT citizen_id FROM citizen_reports WHERE project_id = ?)",
                (project_id, project_id),
            ).fetchone()[0]
            # Concern breakdown: votes.reasons + reports.criteria share the
            # same vocabulary — upvote-why and report-what count as one signal.
            tally: dict[str, int] = {}
            report_tally: dict[str, int] = {}
            for (raw,) in conn.execute(
                "SELECT reasons FROM votes WHERE project_id = ? AND reasons IS NOT NULL",
                (project_id,),
            ):
                try:
                    for rtag in json.loads(str(raw)):
                        tally[str(rtag)] = tally.get(str(rtag), 0) + 1
                except json.JSONDecodeError:
                    pass
            for (raw,) in conn.execute(
                "SELECT criteria FROM citizen_reports WHERE project_id = ?",
                (project_id,),
            ):
                try:
                    for rtag in json.loads(str(raw)):
                        tally[str(rtag)] = tally.get(str(rtag), 0) + 1
                        report_tally[str(rtag)] = report_tally.get(str(rtag), 0) + 1
                except json.JSONDecodeError:
                    pass
            sats = [
                int(r[0])
                for r in conn.execute(
                    "SELECT satisfaction FROM citizen_reports WHERE project_id = ? AND satisfaction IS NOT NULL",
                    (project_id,),
                )
                if r[0] is not None
            ]
        finally:
            conn.close()
        satisfaction_avg = round(sum(sats) / len(sats), 2) if sats else None
    reasons_breakdown = [
        {
            "reason": k,
            "count": v,
            "report_count": report_tally.get(k, 0),
            "upvote_count": v - report_tally.get(k, 0),
        }
        for k, v in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    satisfaction_count = len(sats)

    # Transparent demo formula: up to 40 pts from upvotes (saturating at 40),
    # up to 60 from citizen reports (15 each, saturating at 60).
    psi = min(40, upvotes) + min(60, reports * 15)
    if psi == 0:
        label = "NO_SIGNAL"
    elif psi <= 25:
        label = "LOW"
    elif psi <= 60:
        label = "MODERATE"
    else:
        label = "HIGH"

    return CitizenPsiResponse(
        project_id=project_id,
        upvote_count=upvotes,
        report_count=reports,
        distinct_citizens=int(distinct),
        psi_score=psi,
        label=label,
        reasons_breakdown=reasons_breakdown,
        satisfaction_avg=satisfaction_avg,
        satisfaction_count=satisfaction_count,
        methodology="Demo formula: min(40, upvotes) + min(60, 15 x citizen reports). Measures public participation volume only.",
        disclaimer="Public Satisfaction Indicator is a demo participation signal — NOT a detection engine and NOT part of the risk score.",
    )


@router.get("/overview", response_model=CitizenOverviewResponse)
def citizen_overview():
    """Portal participation stats (Overview tab)."""
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    _ensure_seeded()
    vcounts = _vote_counts()
    rcounts = _report_counts()

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_tables(conn)
            total_citizens = conn.execute("SELECT COUNT(*) c FROM citizens").fetchone()[0]
            total_upvotes = conn.execute("SELECT COUNT(*) c FROM votes").fetchone()[0]
            total_reports = conn.execute("SELECT COUNT(*) c FROM citizen_reports").fetchone()[0]
            engaged = conn.execute(
                "SELECT COUNT(DISTINCT project_id) c FROM (SELECT project_id FROM votes UNION SELECT project_id FROM citizen_reports)"
            ).fetchone()[0]
            recent_rows = conn.execute(
                "SELECT * FROM citizen_reports ORDER BY id DESC LIMIT 6"
            ).fetchall()
        finally:
            conn.close()

    def _mk_item(row: pd.Series, v: int, r: int) -> CitizenFeedItem:
        return _feed_item(row, v, r, None)

    top_ids = sorted(vcounts, key=lambda k: vcounts[k], reverse=True)[:5]
    top_items: list[CitizenFeedItem] = []
    for pid in top_ids:
        match = df[df["project_id"].astype(str) == pid]
        if match.empty:
            continue
        row = match.iloc[0]
        wd = row.get("work_description")
        if (wd is None or pd.isna(wd)) and data_store.master_works is not None and "work_description" in data_store.master_works.columns:
            mwm = data_store.master_works[data_store.master_works["project_id"].astype(str) == pid]
            if not mwm.empty:
                row = row.copy()
                row["work_description"] = mwm.iloc[0]["work_description"]
        top_items.append(_mk_item(row, vcounts[pid], rcounts.get(pid, 0)))

    emap: dict[str, pd.Series] = {}
    ids = list({str(r["project_id"]) for r in recent_rows})
    if ids:
        sub = df[df["project_id"].astype(str).isin(ids)].drop_duplicates(subset=["project_id"])
        emap = {str(r["project_id"]): r for _, r in sub.iterrows()}
    recent_items = [_report_row_to_item(r, emap.get(str(r["project_id"]))) for r in recent_rows]

    # Participation by state (simple counts of engaged works per state)
    by_state: dict[str, int] = {}
    engaged_ids = list(set(list(vcounts.keys()) + list(rcounts.keys())))
    if engaged_ids:
        sub = df[df["project_id"].astype(str).isin(engaged_ids)]
        for s, c in sub["state"].value_counts().items():
            by_state[str(s)] = int(c)
    by_state_list = [
        {"state": s, "engaged_works": c}
        for s, c in sorted(by_state.items(), key=lambda kv: kv[1], reverse=True)[:10]
    ]

    return CitizenOverviewResponse(
        total_citizens=int(total_citizens),
        total_upvotes=int(total_upvotes),
        total_reports=int(total_reports),
        works_engaged=int(engaged),
        top_upvoted=top_items,
        recent_reports=recent_items,
        by_state=by_state_list,
        demo_seed=True,
        demo_notice="Demo data: citizen participation shown here is synthetic seed + demo submissions, clearly labeled.",
    )


# Serve uploaded citizen images (demo-grade; uploads dir is gitignored).
# Mounted lazily so tests can redirect the dir via env var.
@router.get("/uploads/{filename}")
def get_upload(filename: str):
    from fastapi.responses import FileResponse

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=422, detail="Invalid filename")
    path = _upload_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)
