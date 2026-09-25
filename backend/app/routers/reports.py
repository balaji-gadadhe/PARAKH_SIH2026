"""
reports.py
==========
Report routing — "a higher authority reports a work → the responsible
authority sees it in their Alerts tab inbox" (demo feature, SQLite-backed).

Endpoints:
- POST /api/reports            — report a flagged work to a responsible authority
- GET  /api/reports            — inbox: reports addressed to the viewer (role+scope)
- POST /api/reports/{id}/ack   — viewer acknowledges/dismisses a report

Storage: SQLite at backend/reports.db (stdlib sqlite3 — no new dependencies;
D-027's frozen CSV layer is untouched). The db file is gitignored. Tests can
redirect it with the PARAKH_REPORTS_DB env var (read lazily per connection).

Routing (deterministic, from the work's own data):
- target MP    → inbox key ("mp",   <mp_name>)       — the work's own MP
- target SNO   → inbox key ("sno",  <state>)          — the work's state
- target DM    → inbox key ("dm",   <constituency>)   — demo proxy (no district data, D-012)
- target MoSPI → inbox key ("mospi","*")              — central audit cell
Inbox visibility: role + scope must match the stored inbox key exactly —
a report addressed to MP X is visible only when ?role=mp&mp=X.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..data_loader import data_store
from ..schemas import (
    ProjectHistoryResponse,
    ReportCreate,
    ReportEvent,
    ReportItem,
    ReportListResponse,
)

router = APIRouter()

_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "reports.db"


def _db_path() -> Path:
    """Reports db location (PARAKH_REPORTS_DB env override for tests)."""
    env = os.environ.get("PARAKH_REPORTS_DB")
    return Path(env) if env else _DEFAULT_DB_PATH

# Report modal authority option → inbox target_type
_ROLE_TO_TARGET_TYPE = {
    "MP": "mp",
    "District Magistrate": "dm",
    "State Nodal Officer": "sno",
    "MoSPI Audit Cell": "mospi",
}

# Single-writer lock: SQLite handles concurrent readers, but writes are
# serialized app-side to avoid "database is locked" under demo load.
_DB_LOCK = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    """Create the reports table; self-heal pre-D-031 dbs via ALTER TABLE."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            reported_by_role TEXT NOT NULL,
            target_role TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_key TEXT NOT NULL,
            comment TEXT,
            summary_md TEXT,
            summary_json TEXT,
            status TEXT NOT NULL DEFAULT 'NEW',
            created_at TEXT NOT NULL,
            acknowledged_at TEXT
        )
        """
    )
    # Idempotent migration for existing demo dbs (Session 14 era: no
    # summary_md / acknowledged_at columns; D-031 Step-1 follow-up: no
    # summary_json). SQLite ALTER TABLE ADD COLUMN raises OperationalError
    # if the column already exists — that's fine.
    for stmt in (
        "ALTER TABLE reports ADD COLUMN summary_md TEXT",
        "ALTER TABLE reports ADD COLUMN acknowledged_at TEXT",
        "ALTER TABLE reports ADD COLUMN summary_json TEXT",
    ):
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column exists
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lookup_project(project_id: str) -> pd.Series:
    """Find the work in risk_results (404 if absent, 503 if data not loaded)."""
    df = data_store.risk_results
    if df is None or df.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")
    matches = df.loc[df["project_id"].astype(str) == project_id]
    if matches.empty:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    return matches.iloc[0]


def _resolve_target_key(project_row: pd.Series, target_role: str) -> tuple[str, str]:
    """Map (work, target_role) → (target_type, target_key) for inbox routing."""
    target_type = _ROLE_TO_TARGET_TYPE.get(target_role)
    if target_type is None:
        raise HTTPException(status_code=422, detail=f"Unknown target_role: {target_role}")

    if target_type == "mp":
        key = str(project_row.get("mp_name", "") or "").strip()
        if not key:
            raise HTTPException(status_code=422, detail="Work has no MP name — cannot route to MP")
        return ("mp", key)
    if target_type == "sno":
        key = str(project_row.get("state", "") or "").strip()
        if not key:
            raise HTTPException(status_code=422, detail="Work has no state — cannot route to SNO")
        return ("sno", key)
    if target_type == "dm":
        key = str(project_row.get("constituency", "") or "").strip()
        if not key:
            raise HTTPException(status_code=422, detail="Work has no constituency — cannot route to DM (demo proxy)")
        return ("dm", key)
    return ("mospi", "*")


def _viewer_to_inbox_key(
    role: str,
    mp: Optional[str],
    state: Optional[str],
) -> tuple[str, str]:
    """Map the viewer's role+scope → the inbox key they may see.

    URL params use the login roles (mp/dm/sno/mospi) — see frontend login.
    """
    role_l = (role or "").strip().lower()
    if role_l in ("mp", "dm"):
        key = (mp or "").strip()
        if not key:
            raise HTTPException(status_code=422, detail=f"role={role_l} requires the mp (identity) query param")
        return ("dm" if role_l == "dm" else "mp", key)
    if role_l == "sno":
        key = (state or "").strip()
        if not key:
            raise HTTPException(status_code=422, detail="role=sno requires the state query param")
        return ("sno", key)
    if role_l in ("mospi", "mo spi"):
        return ("mospi", "*")
    raise HTTPException(status_code=422, detail=f"Unknown role: {role}")


def _enrich_map(project_ids: list[str]) -> dict[str, pd.Series]:
    """project_id → risk_results row (first occurrence), for inbox display fields."""
    df = data_store.risk_results
    if df is None or df.empty or not project_ids:
        return {}
    mask = df["project_id"].astype(str).isin(project_ids)
    sub = df.loc[mask].drop_duplicates(subset=["project_id"])
    return {str(r["project_id"]): r for _, r in sub.iterrows()}


def _row_to_item(row: sqlite3.Row, enrich: Optional[pd.Series]) -> ReportItem:
    if enrich is not None:
        score = float(enrich.get("overall_risk_score", 0) or 0)
        mp_name = str(enrich.get("mp_name", "") or "")
        state = str(enrich.get("state", "") or "")
        category = str(enrich.get("risk_category", "") or "")
    else:
        score, mp_name, state, category = 0.0, "", "", ""

    def _col(name: str) -> Optional[str]:
        """Read a column that may not exist in a pre-D-031 db (self-heals on next write)."""
        try:
            v = row[name]
        except (IndexError, KeyError):
            return None
        return str(v) if v is not None else None

    return ReportItem(
        id=int(row["id"]),
        project_id=str(row["project_id"]),
        reported_by_role=str(row["reported_by_role"]),
        target_role=str(row["target_role"]),
        comment=row["comment"],
        summary_md=_col("summary_md"),
        summary_json=_col("summary_json"),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        acknowledged_at=_col("acknowledged_at"),
        mp_name=mp_name,
        state=state,
        risk_score_display=round(score * 100),
        risk_category=category,
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=ReportListResponse)
def list_reports(
    role: str = Query(..., description="Viewer role: mp | dm | sno | mospi"),
    mp: Optional[str] = Query(None, description="Identity name (role=mp/dm)"),
    state: Optional[str] = Query(None, description="State name (role=sno)"),
    status: Optional[str] = Query(None, description="Filter: NEW | ACKNOWLEDGED"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Inbox: reports addressed to the viewer's role+scope (NEW + ACKNOWLEDGED)."""
    target_type, target_key = _viewer_to_inbox_key(role, mp, state)

    # Self-heal a pre-D-031 db on the first read of this process (cheap: no-op
    # once the columns exist). Keeps the demo db backward-compatible.
    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
        finally:
            conn.close()

    where = "target_type = ? AND target_key = ?"
    params: list = [target_type, target_key]
    if status:
        where += " AND status = ?"
        params.append(status.upper())

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            total = conn.execute(
                f"SELECT COUNT(*) FROM reports WHERE {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM reports WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [page_size, (page - 1) * page_size],
            ).fetchall()
        finally:
            conn.close()

    emap = _enrich_map([str(r["project_id"]) for r in rows])
    items = [_row_to_item(r, emap.get(str(r["project_id"]))) for r in rows]
    return ReportListResponse(total=total, items=items, page=page, page_size=page_size)


@router.post("", response_model=ReportItem)
def create_report(payload: ReportCreate):
    """Higher authority reports a work → store + route to the responsible authority."""
    project_row = _lookup_project(payload.project_id)
    target_type, target_key = _resolve_target_key(project_row, payload.target_role)
    now = _now_iso()

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            cur = conn.execute(
                "INSERT INTO reports (project_id, reported_by_role, target_role, target_type, target_key, comment, summary_md, summary_json, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?)",
                (
                    payload.project_id,
                    payload.reported_by_role[:64],
                    payload.target_role[:64],
                    target_type,
                    target_key,
                    (payload.comment or None),
                    (payload.summary_md or None),
                    (payload.summary_json or None),
                    now,
                ),
            )
            report_id = cur.lastrowid
            conn.commit()
        finally:
            conn.close()

    stored = {
        "id": report_id,
        "project_id": payload.project_id,
        "reported_by_role": payload.reported_by_role[:64],
        "target_role": payload.target_role[:64],
        "comment": payload.comment,
        "summary_md": payload.summary_md,
        "summary_json": payload.summary_json,
        "status": "NEW",
        "created_at": now,
    }
    return _row_to_item(stored, project_row)  # type: ignore[arg-type]


@router.post("/clear")
def clear_reports(
    role: str = Query(..., description="Viewer role: mp | dm | sno | mospi"),
    mp: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="Clear only NEW or ACKNOWLEDGED; default = all"),
):
    """Clear (hard-delete) reports in the viewer's own inbox — demo-grade reset.

    Scope rules are identical to the inbox: only reports addressed to the
    caller's role+scope are removed; other authorities' reports are untouched.
    """
    target_type, target_key = _viewer_to_inbox_key(role, mp, state)

    where = "target_type = ? AND target_key = ?"
    params: list = [target_type, target_key]
    if status:
        where += " AND status = ?"
        params.append(status.upper())

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            cur = conn.execute(f"DELETE FROM reports WHERE {where}", params)
            conn.commit()
            deleted = cur.rowcount
        finally:
            conn.close()

    return {"ok": True, "deleted": deleted}


@router.post("/{report_id}/ack")
def ack_report(
    report_id: int,
    role: str = Query(..., description="Viewer role: mp | dm | sno | mospi"),
    mp: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """Target authority acknowledges (marks reviewed) a report in their inbox."""
    target_type, target_key = _viewer_to_inbox_key(role, mp, state)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT id FROM reports WHERE id = ? AND target_type = ? AND target_key = ?",
                (report_id, target_type, target_key),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Report not found in your inbox: {report_id}")
            conn.execute(
                "UPDATE reports SET status = 'ACKNOWLEDGED', acknowledged_at = ? WHERE id = ?",
                (_now_iso(), report_id),
            )
            conn.commit()
        finally:
            conn.close()

    return {"ok": True, "id": report_id, "status": "ACKNOWLEDGED"}


@router.get("/{report_id}/summary")
def get_report_summary(
    report_id: int,
    role: str = Query(..., description="Viewer role: mp | dm | sno | mospi"),
    mp: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """Fetch the analysis snapshot attached to a report (D-031 Step 1).

    Scope rule: identical to inbox visibility — only the report's target
    authority can read it.
    """
    target_type, target_key = _viewer_to_inbox_key(role, mp, state)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            row = conn.execute(
                "SELECT summary_md, summary_json, status, created_at, acknowledged_at, reported_by_role, target_role, project_id, comment "
                "FROM reports WHERE id = ? AND target_type = ? AND target_key = ?",
                (report_id, target_type, target_key),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"Report not found in your inbox: {report_id}")
        finally:
            conn.close()

    def _s(name: str) -> Optional[str]:
        v = row[name]
        return str(v) if v is not None else None

    return {
        "report_id": report_id,
        "project_id": _s("project_id"),
        "status": _s("status"),
        "created_at": _s("created_at"),
        "acknowledged_at": _s("acknowledged_at"),
        "reported_by_role": _s("reported_by_role"),
        "target_role": _s("target_role"),
        "comment": _s("comment"),
        "summary_md": _s("summary_md"),
        "summary_json": _s("summary_json"),
    }


@router.get("/history/{project_id}", response_model=ProjectHistoryResponse)
def get_project_history(project_id: str):
    """Investigation history for one work (D-031 Step 3): every report raised
    against it + current status, newest first — the "what action has been
    taken after reporting" trail shown on the dossier.

    Note: no auth in the demo (accepted limitation since D-029) — this is the
    same data the inboxes already expose, grouped per work. The work itself
    must exist in risk_results (404 otherwise) so the endpoint doubles as a
    validity check for the dossier's timeline tab.
    """
    project_row = _lookup_project(project_id)

    with _DB_LOCK:
        conn = _get_conn()
        try:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT * FROM reports WHERE project_id = ? ORDER BY id DESC",
                (project_id,),
            ).fetchall()
        finally:
            conn.close()

    score = float(project_row.get("overall_risk_score", 0) or 0)
    events = [
        ReportEvent(
            id=int(r["id"]),
            reported_by_role=str(r["reported_by_role"]),
            target_role=str(r["target_role"]),
            comment=str(r["comment"]) if r["comment"] else None,
            has_snapshot=bool(r["summary_md"] or _safe_col(r, "summary_json")),
            status=str(r["status"]),
            created_at=str(r["created_at"]),
            acknowledged_at=_safe_col(r, "acknowledged_at"),
        )
        for r in rows
    ]
    return ProjectHistoryResponse(
        project_id=project_id,
        mp_name=str(project_row.get("mp_name", "") or ""),
        state=str(project_row.get("state", "") or ""),
        risk_category=str(project_row.get("risk_category", "") or ""),
        risk_score_display=round(score * 100),
        total_reports=len(events),
        new_reports=sum(1 for e in events if e.status == "NEW"),
        events=events,
    )


def _safe_col(row: sqlite3.Row, name: str) -> Optional[str]:
    """Read a possibly-missing column from a row (pre-migration dbs)."""
    try:
        v = row[name]
    except (IndexError, KeyError):
        return None
    return str(v) if v is not None else None
