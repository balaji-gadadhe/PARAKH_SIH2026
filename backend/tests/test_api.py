"""
test_api.py
===========
Smoke tests for all PARAKH FastAPI endpoints.
Uses TestClient (httpx) to test endpoints without starting a server.

Run from repo root:
    cd SIH-2026
    python -m pytest backend/tests/test_api.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure the project root is on sys.path so imports resolve
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Create a TestClient that triggers the lifespan (data loading)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def critical_detail(client):
    """Detail payload of one CRITICAL project (shared across detail tests)."""
    list_resp = client.get("/api/projects", params={"tier": "CRITICAL", "page_size": 1})
    project_id = list_resp.json()["items"][0]["project_id"]
    resp = client.get(f"/api/projects/{project_id}")
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture(scope="module")
def harbhajan_detail(client):
    """MP detail for the card-reference example MP (120 works, Punjab)."""
    resp = client.get("/api/mps/Shri Harbhajan Singh (2022-28)")
    assert resp.status_code == 200
    return resp.json()


# ─── Root & Health ────────────────────────────────────────────────────────────

class TestRootAndHealth:
    def test_root_returns_api_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "PARAKH API"
        assert body["version"] == "0.1.0"
        assert body["status"] == "healthy"

    def test_health_returns_loaded_status(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["loaded"] is True
        assert body["risk_results_rows"] > 0


# ─── Dashboard ────────────────────────────────────────────────────────────────

class TestDashboard:
    def test_summary_has_all_fields(self, client):
        resp = client.get("/api/dashboard/summary")
        assert resp.status_code == 200
        body = resp.json()
        # KPI fields
        assert body["total_works"] == 86976
        assert body["total_mps"] > 0
        assert body["funds_allocated"] > 0
        assert body["funds_utilized"] >= 0
        assert 0 <= body["utilization_pct"] <= 100
        assert body["completed_works"] >= 0
        assert 0 <= body["completion_pct"] <= 100
        assert body["avg_financial_progress"] >= 0
        # Distribution
        tier_dist = body["tier_distribution"]
        assert "CRITICAL" in tier_dist
        assert "HIGH" in tier_dist
        assert "MEDIUM" in tier_dist
        assert "LOW" in tier_dist
        assert sum(tier_dist.values()) == 86976
        # Top lists
        assert isinstance(body["top_states_by_risk"], list)
        assert isinstance(body["top_mps_by_flagged"], list)


# ─── Projects ─────────────────────────────────────────────────────────────────

class TestProjects:
    def test_list_returns_paginated_results(self, client):
        resp = client.get("/api/projects", params={"page": 1, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 86976
        assert body["page"] == 1
        assert body["page_size"] == 5
        assert body["pages"] > 1000
        assert len(body["items"]) == 5

    def test_list_item_has_required_fields(self, client):
        resp = client.get("/api/projects", params={"page": 1, "page_size": 1})
        item = resp.json()["items"][0]
        assert "project_id" in item
        assert "mp_name" in item
        assert "state" in item
        assert "overall_risk_score" in item
        assert "risk_score_display" in item
        assert "risk_category" in item
        assert 0 <= item["risk_score_display"] <= 100

    def test_list_filter_by_tier(self, client):
        resp = client.get("/api/projects", params={"tier": "CRITICAL", "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 24
        for item in body["items"]:
            assert item["risk_category"] == "CRITICAL"

    def test_list_filter_by_min_score(self, client):
        resp = client.get("/api/projects", params={"min_score": 80, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["risk_score_display"] >= 80

    def test_list_sort_by_amount(self, client):
        resp = client.get("/api/projects", params={"sort": "amount_desc", "page_size": 5})
        assert resp.status_code == 200
        items = resp.json()["items"]
        amounts = [i["recommended_amount"] for i in items]
        assert amounts == sorted(amounts, reverse=True)

    def test_list_filter_by_state(self, client):
        resp = client.get("/api/projects", params={"state": "Punjab", "page_size": 3})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "punjab" in item["state"].lower()

    def test_detail_returns_full_project(self, client):
        # Get the first project from the list
        list_resp = client.get("/api/projects", params={"page_size": 1})
        project_id = list_resp.json()["items"][0]["project_id"]
        # Fetch detail
        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["project_id"] == project_id
        assert "audit_explanation" in detail
        assert "engines" in detail
        assert len(detail["engines"]) == 6
        # Each engine has score/flag/available
        for engine in detail["engines"]:
            assert "engine" in engine
            assert "score" in engine
            assert "flag" in engine
            assert "available" in engine

    def test_detail_critical_project(self, client):
        # Get a CRITICAL project
        list_resp = client.get("/api/projects", params={"tier": "CRITICAL", "page_size": 1})
        project_id = list_resp.json()["items"][0]["project_id"]
        resp = client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["risk_category"] == "CRITICAL"
        assert detail["risk_score_display"] >= 80
        assert detail["audit_explanation"] is not None
        assert len(detail["audit_explanation"]) > 10

    def test_detail_not_found(self, client):
        resp = client.get("/api/projects/nonexistent_id_xyz")
        assert resp.status_code == 404

    def test_search_by_project_id(self, client):
        # Get a project_id from the list, then search for it
        list_resp = client.get("/api/projects", params={"page_size": 1})
        pid = list_resp.json()["items"][0]["project_id"]
        # Search with just the first part of the ID
        search_term = pid.split("|")[0]
        resp = client.get("/api/projects", params={"q": search_term, "page_size": 5})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


# ─── MPs ──────────────────────────────────────────────────────────────────────

class TestMPs:
    def test_list_returns_mps(self, client):
        resp = client.get("/api/mps")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] > 0
        assert len(body["items"]) > 0

    def test_list_mp_has_fields(self, client):
        resp = client.get("/api/mps", params={"sort": "flagged_desc"})
        mp = resp.json()["items"][0]
        assert "mp_name" in mp
        assert "state" in mp
        assert "recommended_works" in mp
        assert "flagged_works" in mp
        assert mp["recommended_works"] > 0

    def test_list_filter_by_state(self, client):
        resp = client.get("/api/mps", params={"state": "Punjab"})
        assert resp.status_code == 200
        for mp in resp.json()["items"]:
            assert "punjab" in mp["state"].lower()

    def test_list_sort_by_flagged(self, client):
        resp = client.get("/api/mps", params={"sort": "flagged_desc"})
        items = resp.json()["items"]
        flagged = [i["flagged_works"] for i in items]
        assert flagged == sorted(flagged, reverse=True)

    def test_detail_returns_mp_with_works(self, client):
        # Get top MP name
        list_resp = client.get("/api/mps", params={"sort": "flagged_desc", "page_size": 1})
        mp_name = list_resp.json()["items"][0]["mp_name"]
        resp = client.get(f"/api/mps/{mp_name}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["mp"]["mp_name"] == mp_name
        assert len(detail["works"]) > 0
        # Works should be sorted by risk (highest first)
        scores = [w["risk_score_display"] for w in detail["works"]]
        assert scores == sorted(scores, reverse=True)

    def test_detail_not_found(self, client):
        resp = client.get("/api/mps/Nonexistent_MP_12345")
        assert resp.status_code == 404


# ─── Alerts ───────────────────────────────────────────────────────────────────

class TestAlerts:
    def test_alerts_returns_flagged_projects(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 182  # 158 HIGH + 24 CRITICAL
        assert "tier_counts" in body
        assert body["tier_counts"]["CRITICAL"] == 24
        assert body["tier_counts"]["HIGH"] == 158

    def test_alerts_has_signal_aggregates(self, client):
        resp = client.get("/api/alerts")
        body = resp.json()
        assert len(body["signal_aggregates"]) > 0
        for sig in body["signal_aggregates"]:
            assert "signal" in sig
            assert "count" in sig
            assert sig["count"] > 0

    def test_alerts_filter_by_tier(self, client):
        resp = client.get("/api/alerts", params={"tier": "CRITICAL"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 24
        for item in body["items"]:
            assert item["risk_category"] == "CRITICAL"

    def test_alerts_filter_by_min_score(self, client):
        resp = client.get("/api/alerts", params={"min_score": 85})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["risk_score_display"] >= 85

    def test_alerts_sorted_by_score_desc(self, client):
        resp = client.get("/api/alerts")
        items = resp.json()["items"]
        scores = [i["risk_score_display"] for i in items]
        assert scores == sorted(scores, reverse=True)

    def test_alerts_item_has_required_fields(self, client):
        resp = client.get("/api/alerts", params={"tier": "CRITICAL", "page_size": 1})
        item = resp.json()["items"][0]
        assert "project_id" in item
        assert "mp_name" in item
        assert "state" in item
        assert "risk_score_display" in item
        assert "top_risk_signals" in item
        assert item["recommended_amount"] > 0


# ─── Agencies ────────────────────────────────────────────────────────────────

class TestAgencies:
    def test_list_returns_agencies(self, client):
        resp = client.get("/api/agencies")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] > 0
        assert len(body["items"]) > 0

    def test_list_item_has_fields(self, client):
        resp = client.get("/api/agencies", params={"page_size": 1})
        item = resp.json()["items"][0]
        assert "agency_id" in item
        assert "agency_risk_score" in item
        assert "agency_risk_level" in item

    def test_list_filter_by_risk_level(self, client):
        resp = client.get("/api/agencies", params={"risk_level": "HIGH"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["agency_risk_level"] == "HIGH"

    def test_list_sort_by_risk_desc(self, client):
        resp = client.get("/api/agencies", params={"sort": "risk_desc"})
        items = resp.json()["items"]
        scores = [i["agency_risk_score"] for i in items if i["agency_risk_score"] is not None]
        assert scores == sorted(scores, reverse=True)

    def test_list_search_by_name(self, client):
        resp = client.get("/api/agencies", params={"q": "construction", "page_size": 5})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert "construction" in item["agency_id"].lower()

    def test_detail_returns_full_agency(self, client):
        list_resp = client.get("/api/agencies", params={"page_size": 1})
        agency_id = list_resp.json()["items"][0]["agency_id"]
        resp = client.get(f"/api/agencies/{agency_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["agency_id"] == agency_id
        assert "total_projects" in detail
        assert "completion_rate" in detail
        assert "agency_risk_score" in detail
        assert "risk_reasons" in detail

    def test_detail_not_found(self, client):
        resp = client.get("/api/agencies/nonexistent_agency_xyz")
        assert resp.status_code == 404


# ─── Projects: list fields & filters (docs/frontend-skeleton.md §2) ──────────

class TestProjectListNewFields:
    def test_list_items_have_work_description_and_status(self, client):
        resp = client.get("/api/projects", params={"page_size": 5})
        items = resp.json()["items"]
        for item in items:
            assert "work_description" in item
            assert "status" in item
        # master_works covers all 86,976 projects — descriptions must be present
        assert all(i["work_description"] for i in items)

    def test_status_filter_completed(self, client):
        resp = client.get("/api/projects", params={"status": "completed", "page_size": 10})
        body = resp.json()
        assert body["total"] == 128  # 128 completed works in the data
        for item in body["items"]:
            assert item["is_completed"] == 1

    def test_status_filter_ongoing(self, client):
        resp = client.get("/api/projects", params={"status": "ongoing", "page_size": 5})
        body = resp.json()
        assert body["total"] == 86976 - 128
        for item in body["items"]:
            assert item["is_completed"] == 0

    def test_category_filter(self, client):
        resp = client.get("/api/projects", params={"category": "Repair and Renovation", "page_size": 5})
        body = resp.json()
        assert body["total"] == 1344
        for item in body["items"]:
            assert "repair" in item["category"].lower()

    def test_search_matches_work_description(self, client):
        resp = client.get("/api/projects", params={"q": "school", "page_size": 10})
        body = resp.json()
        assert body["total"] > 0
        for item in body["items"]:
            desc = (item["work_description"] or "").lower()
            assert "school" in desc or "school" in item["project_id"].lower()


# ─── Projects: detail investigation-view fields (docs/frontend_card_reference.md §2) ─

class TestProjectDetailNewFields:
    def test_investigation_fields(self, critical_detail):
        assert critical_detail["investigation_priority"] is not None
        assert 0 <= critical_detail["investigation_priority"] <= 100
        assert critical_detail["investigation_urgency"] in (
            "TIER_1_IMMEDIATE_ACTION",
            "TIER_2_PRIORITY_INSPECTION",
            "TIER_3_DESK_REVIEW",
            "TIER_4_ROUTINE",
        )
        assert isinstance(critical_detail["audit_dispatch_recommended"], bool)
        # CRITICAL projects are always TIER_1 (risk_score >= 0.70)
        assert critical_detail["investigation_urgency"] == "TIER_1_IMMEDIATE_ACTION"
        assert critical_detail["audit_dispatch_recommended"] is True

    def test_financial_fields(self, critical_detail):
        # Peer-cost fields come from project_features — populated for real works
        for field in (
            "final_amount", "cost_variation_pct", "peer_median_cost",
            "peer_mean_cost", "peer_std_cost", "cost_deviation_from_peer",
        ):
            assert field in critical_detail
        assert critical_detail["peer_median_cost"] is not None
        assert critical_detail["peer_mean_cost"] is not None

    def test_payment_fields(self, critical_detail):
        for field in (
            "payment_count", "average_payment", "maximum_payment",
            "minimum_payment", "payment_frequency", "successful_payment_count",
            "pending_payment_count", "latest_payment_status",
        ):
            assert field in critical_detail
        assert critical_detail["payment_count"] is not None
        assert critical_detail["payment_count"] >= 0

    def test_vendor_and_other_fields(self, critical_detail):
        for field in (
            "primary_vendor", "vendor_risk_score", "vendor_risk_level",
            "days_since_recommendation", "recommendation_to_completion_days",
            "average_rating", "has_images", "ida",
            "description_similarity_score", "work_description", "status",
        ):
            assert field in critical_detail
        assert critical_detail["work_description"] is not None
        assert isinstance(critical_detail["has_images"], bool)
        assert isinstance(critical_detail["ida"], bool)

    def test_identity_fields_complete(self, critical_detail):
        for field in ("project_id", "mp_name", "state", "constituency", "category"):
            assert critical_detail[field]


# ─── MPs: MP card fields (docs/frontend_card_reference.md §1) ─────────────────

class TestMPCardFields:
    def test_card_header_fields(self, harbhajan_detail):
        mp = harbhajan_detail["mp"]
        assert mp["mp_name"] == "Shri Harbhajan Singh (2022-28)"
        assert mp["state"] == "Punjab"
        assert mp["recommended_works"] == 120  # card reference example: 120 works

    def test_card_risk_counts(self, harbhajan_detail):
        # Card reference example: 6 critical / 0 high / 31 medium / 83 low
        assert harbhajan_detail["critical_works"] == 6
        assert harbhajan_detail["high_risk_works"] == 0
        assert harbhajan_detail["medium_risk_works"] == 31
        assert harbhajan_detail["low_risk_works"] == 83
        assert harbhajan_detail["total_works"] == 120
        # Tier counts partition the MP's works exactly
        assert (
            harbhajan_detail["critical_works"]
            + harbhajan_detail["high_risk_works"]
            + harbhajan_detail["medium_risk_works"]
            + harbhajan_detail["low_risk_works"]
            == harbhajan_detail["total_works"]
        )
        assert len(harbhajan_detail["works"]) == harbhajan_detail["total_works"]

    def test_card_risk_scores(self, harbhajan_detail):
        # Card reference example: avg 24.58 / highest 89.84
        assert harbhajan_detail["average_risk_score"] == pytest.approx(24.58, abs=0.01)
        assert harbhajan_detail["highest_work_risk"] == pytest.approx(89.84, abs=0.01)

    def test_card_financial_fields(self, harbhajan_detail):
        mp = harbhajan_detail["mp"]
        assert mp["allocated_amount"] is not None
        assert mp["total_expenditure"] is not None
        assert mp["utilization_pct"] is not None
        assert mp["pending_payments"] is not None
        assert mp["total_expenditure"] >= 0

    def test_list_items_have_master_fields(self, client):
        resp = client.get("/api/mps", params={"page_size": 20})
        items = resp.json()["items"]
        assert len(items) > 0
        for mp in items:
            assert mp["total_expenditure"] is not None
            assert mp["pending_payments"] is not None
            assert mp["allocated_amount"] is not None

    def test_house_filter(self, client):
        resp = client.get("/api/mps", params={"house": "Rajya Sabha"})
        body = resp.json()
        assert body["total"] > 0
        for mp in body["items"]:
            assert mp["house"] == "Rajya Sabha"

    def test_completion_sort(self, client):
        resp = client.get("/api/mps", params={"sort": "completion_desc"})
        items = resp.json()["items"]
        rates = [i["completion_rate_pct"] for i in items if i["completion_rate_pct"] is not None]
        assert rates == sorted(rates, reverse=True)


# ─── Alerts: pagination & search (docs/frontend-skeleton.md §4) ──────────────

class TestAlertsPagination:
    def test_pagination_fields(self, client):
        resp = client.get("/api/alerts", params={"page": 1, "page_size": 50})
        body = resp.json()
        assert body["total"] == 182
        assert body["pages"] == 4
        assert len(body["items"]) == 50
        assert body["page"] == 1
        assert body["page_size"] == 50

    def test_page_beyond_last_returns_empty(self, client):
        resp = client.get("/api/alerts", params={"page": 9, "page_size": 50})
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 182  # aggregates still reflect the full set

    def test_aggregates_cover_full_filtered_set(self, client):
        resp = client.get("/api/alerts", params={"page": 2, "page_size": 50})
        body = resp.json()
        # Tier counts computed over ALL 182, not just the page of 50
        assert body["tier_counts"]["CRITICAL"] == 24
        assert body["tier_counts"]["HIGH"] == 158
        assert len(body["signal_aggregates"]) > 0

    def test_search_by_project_id(self, client):
        list_resp = client.get("/api/alerts", params={"page_size": 1})
        pid = list_resp.json()["items"][0]["project_id"]
        fragment = pid.split("|")[0]
        resp = client.get("/api/alerts", params={"q": fragment})
        body = resp.json()
        assert body["total"] >= 1
        assert any(fragment in i["project_id"] for i in body["items"])

    def test_mp_filter(self, client):
        list_resp = client.get("/api/alerts", params={"page_size": 1})
        mp_name = list_resp.json()["items"][0]["mp_name"]
        resp = client.get("/api/alerts", params={"mp": mp_name})
        body = resp.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["mp_name"] == mp_name
