"""
test_dashboard.py
=================
Tests for the dashboard endpoints — including the D-031 Step-2a state risk
aggregation (GET /api/dashboard/states) that powers the India map.

Run from repo root:
    python -m pytest backend/tests/test_dashboard.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# Frozen demo numbers (D-027) — the state endpoint must aggregate to these.
EXPECTED_TIER_TOTALS = {"LOW": 73013, "MEDIUM": 13781, "HIGH": 158, "CRITICAL": 24}
EXPECTED_TOTAL_WORKS = 86976


class TestDashboardSummary:
    def test_summary_frozen_numbers(self, client):
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_works"] == EXPECTED_TOTAL_WORKS
        assert body["total_mps"] == 731
        for tier, n in EXPECTED_TIER_TOTALS.items():
            assert body["tier_distribution"][tier] == n


class TestStateRisk:
    """D-031 Step 2a — GET /api/dashboard/states."""

    def test_returns_states(self, client):
        resp = client.get("/api/dashboard/states")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_states"] > 20  # India has 28+8; data covers most
        assert len(body["states"]) == body["total_states"]

    def test_works_sum_to_frozen_total(self, client):
        body = client.get("/api/dashboard/states").json()
        total = sum(s["total_works"] for s in body["states"])
        assert total == EXPECTED_TOTAL_WORKS

    def test_tiers_sum_to_frozen_distribution(self, client):
        body = client.get("/api/dashboard/states").json()
        for tier in ("low", "medium", "high", "critical"):
            total = sum(s[tier] for s in body["states"])
            assert total == EXPECTED_TIER_TOTALS[tier.upper()]

    def test_high_critical_is_sum_of_parts(self, client):
        body = client.get("/api/dashboard/states").json()
        for s in body["states"]:
            assert s["high_critical"] == s["high"] + s["critical"]

    def test_punjab_present_with_critical(self, client):
        """Worked example 80673 is a CRITICAL Punjab work — Punjab must show ≥1."""
        body = client.get("/api/dashboard/states").json()
        punjab = [s for s in body["states"] if s["state"] == "Punjab"]
        assert punjab, "Punjab missing from state aggregation"
        assert punjab[0]["critical"] >= 1
        assert punjab[0]["flagged_mps"] >= 1

    def test_sorted_by_attention(self, client):
        """Sort: high_critical desc, then total_works desc."""
        body = client.get("/api/dashboard/states").json()
        states = body["states"]
        for a, b in zip(states, states[1:]):
            assert (a["high_critical"], a["total_works"]) >= (b["high_critical"], b["total_works"])

    def test_financials_non_negative(self, client):
        body = client.get("/api/dashboard/states").json()
        for s in body["states"]:
            assert s["funds_allocated"] >= 0
            assert s["funds_utilized"] >= 0
