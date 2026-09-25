"""
mps.py
======
GET /api/mps          — MP summary list (searchable, sortable)
GET /api/mps/{name}   — MP detail + their works + per-tier risk counts

Fields follow docs/frontend-skeleton.md §3 and docs/frontend_card_reference.md §1:
risk-tier counts, average/highest risk score, and payment totals per MP.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..data_loader import data_store
from ..schemas import MpSummary, MpDetail, MpListResponse, ProjectSummary

router = APIRouter()

# Canonical master_mp_summary columns consumed by the MP card.
# master_mp_summary.csv header (verified): mp_name, constituency, state, house,
# allocated_amount, total_expenditure, utilization_pct, completed_works,
# recommended_works, completion_rate_pct, unspent_amount, transaction_count,
# successful_payments, pending_payments, average_rating
_MASTER_MP_COLS = [
    "house", "allocated_amount", "total_expenditure", "utilization_pct",
    "completed_works", "completion_rate_pct", "unspent_amount",
    "pending_payments", "average_rating",
]


def _to_score_display(score: float) -> int:
    return round(score * 100)


def _build_mp_table() -> pd.DataFrame:
    """One row per MP: risk aggregates from risk results + master_mp fields."""
    df_risk = data_store.risk_results

    mp = (
        df_risk.groupby("mp_name")
        .agg(
            state=("state", "first"),
            constituency=("constituency", "first"),
            works=("project_id", "count"),
            flagged_count=("risk_category", lambda x: int((x.isin(["HIGH", "CRITICAL"])).sum())),
            avg_score=("overall_risk_score", "mean"),
            max_score=("overall_risk_score", "max"),
        )
        .reset_index()
    )

    # Per-tier counts (card reference §1: critical/high/medium/low works)
    tier_pivot = df_risk.pivot_table(
        index="mp_name", columns="risk_category", values="project_id", aggfunc="count"
    )
    for tier in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        col = f"{tier.lower()}_count"
        if tier in tier_pivot.columns:
            mp[col] = mp["mp_name"].map(tier_pivot[tier]).fillna(0).astype(int)
        else:
            mp[col] = 0

    # Merge master_mp fields (exact-name match first, then case-insensitive)
    if data_store.master_mp is not None:
        mm = data_store.master_mp.copy()
        mm.columns = [c.strip() for c in mm.columns]
        # Normalize the join key
        name_col = next(
            (c for c in mm.columns if c.lower() in ("mp_name", "mp name", "member_name")),
            None,
        )
        if name_col is None:
            raise HTTPException(status_code=500, detail="master_mp_summary has no mp_name column")
        mm = mm.rename(columns={name_col: "mp_name"})
        mm["mp_name"] = mm["mp_name"].astype(str)

        rename_map = {}
        for canonical in _MASTER_MP_COLS:
            if canonical in mm.columns:
                continue
            match = next(
                (c for c in mm.columns if c.lower().replace(" ", "_") == canonical), None
            )
            if match is not None:
                rename_map[match] = canonical
        mm = mm.rename(columns=rename_map)

        keep = ["mp_name"] + [c for c in _MASTER_MP_COLS if c in mm.columns]
        mm = mm[keep]
        # Drop columns that already exist in mp to avoid _x/_y suffixes
        overlap = [c for c in mm.columns if c != "mp_name" and c in mp.columns]
        mm = mm.drop(columns=overlap)
        mp = mp.merge(mm, on="mp_name", how="left")
    else:
        for c in _MASTER_MP_COLS:
            if c not in mp.columns:
                mp[c] = None

    return mp


def _mp_row_to_summary(r: pd.Series) -> MpSummary:
    def _num(col):
        val = r.get(col)
        try:
            return None if pd.isna(val) else float(val)
        except (TypeError, ValueError):
            return None

    def _int(col):
        val = _num(col)
        return None if val is None else int(round(val))

    return MpSummary(
        mp_name=str(r["mp_name"]),
        state=str(r.get("state", "")),
        constituency=str(r.get("constituency", "")),
        house=str(r["house"]) if pd.notna(r.get("house")) else None,
        recommended_works=int(r["works"]),
        completed_works=_int("completed_works"),
        completion_rate_pct=_num("completion_rate_pct"),
        allocated_amount=_num("allocated_amount"),
        total_expenditure=_num("total_expenditure"),
        utilization_pct=_num("utilization_pct"),
        unspent_amount=_num("unspent_amount"),
        pending_payments=_int("pending_payments"),
        average_rating=_num("average_rating"),
        flagged_works=int(r["flagged_count"]),
    )


@router.get("", response_model=MpListResponse)
def list_mps(
    q: Optional[str] = Query(None, description="Search by MP name"),
    state: Optional[str] = Query(None, description="State filter"),
    house: Optional[str] = Query(None, description="House: Lok Sabha / Rajya Sabha"),
    sort: Optional[str] = Query(
        "flagged_desc",
        description="Sort: flagged_desc, works_desc, utilization_desc, completion_desc",
    ),
):
    if data_store.risk_results is None or data_store.risk_results.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    mp = _build_mp_table()

    # Filters — regex=False: names may contain regex metacharacters, e.g. "(2022-28)"
    if q:
        mp = mp[mp["mp_name"].str.contains(q, case=False, na=False, regex=False)]
    if state:
        mp = mp[mp["state"].str.contains(state, case=False, na=False, regex=False)]
    if house and "house" in mp.columns:
        mp = mp[mp["house"].str.contains(house, case=False, na=False, regex=False)]

    # Sort
    if sort == "works_desc":
        mp = mp.sort_values("works", ascending=False)
    elif sort == "utilization_desc":
        mp = mp.sort_values("utilization_pct", ascending=False, na_position="last")
    elif sort == "completion_desc":
        mp = mp.sort_values("completion_rate_pct", ascending=False, na_position="last")
    else:
        mp = mp.sort_values("flagged_count", ascending=False)

    items = [_mp_row_to_summary(r) for _, r in mp.iterrows()]
    return MpListResponse(total=len(items), items=items)


@router.get("/{mp_name}", response_model=MpDetail)
def get_mp_detail(mp_name: str):
    if data_store.risk_results is None or data_store.risk_results.empty:
        raise HTTPException(status_code=503, detail="Data not loaded")

    mp_table = _build_mp_table()
    match = mp_table[mp_table["mp_name"].str.lower() == mp_name.lower()]
    if match.empty:
        match = mp_table[mp_table["mp_name"].str.contains(mp_name, case=False, na=False, regex=False)]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"MP not found: {mp_name}")

    mp_row = match.iloc[0]
    canonical_name = str(mp_row["mp_name"])
    mp_df = data_store.risk_results[data_store.risk_results["mp_name"] == canonical_name]

    works = []
    for _, r in mp_df.sort_values("overall_risk_score", ascending=False).iterrows():
        works.append(ProjectSummary(
            project_id=str(r["project_id"]),
            mp_name=str(r["mp_name"]),
            state=str(r["state"]),
            constituency=str(r["constituency"]),
            category=str(r.get("category", "")) if pd.notna(r.get("category")) else "",
            recommended_amount=float(r.get("recommended_amount", 0) or 0),
            total_expenditure=float(r.get("total_expenditure", 0) or 0),
            expenditure_ratio=float(r["expenditure_ratio"]) if pd.notna(r.get("expenditure_ratio")) else None,
            is_completed=int(r["is_completed"]) if pd.notna(r.get("is_completed")) else None,
            overall_risk_score=float(r["overall_risk_score"]),
            risk_score_display=_to_score_display(float(r["overall_risk_score"])),
            risk_category=str(r["risk_category"]),
            top_risk_signals=str(r.get("top_risk_signals", "")) if pd.notna(r.get("top_risk_signals")) else None,
        ))

    def _tier_count(col: str) -> int:
        val = mp_row.get(col)
        return int(val) if pd.notna(val) else 0

    avg_score = mp_row.get("avg_score")
    max_score = mp_row.get("max_score")

    return MpDetail(
        mp=_mp_row_to_summary(mp_row),
        works=works,
        total_works=len(mp_df),
        critical_works=_tier_count("critical_count"),
        high_risk_works=_tier_count("high_count"),
        medium_risk_works=_tier_count("medium_count"),
        low_risk_works=_tier_count("low_count"),
        average_risk_score=round(float(avg_score) * 100, 2) if pd.notna(avg_score) else None,
        highest_work_risk=round(float(max_score) * 100, 2) if pd.notna(max_score) else None,
    )
