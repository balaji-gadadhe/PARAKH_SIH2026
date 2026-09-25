"""
test_reports.py
===============
Tests for the reports (notification) system — D-029.

Covers: create → route → inbox visibility per role/scope → ack, plus
validation errors. Uses a temp SQLite db via PARAKH_REPORTS_DB so the
runtime backend/reports.db is never touched.

Run from repo root:
    python -m pytest backend/tests/test_reports.py -v
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """TestClient + temp reports db for this module."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PARAKH_REPORTS_DB"] = str(Path(tmp) / "test_reports.db")
        with TestClient(app) as c:
            yield c
        os.environ.pop("PARAKH_REPORTS_DB", None)


@pytest.fixture(scope="module")
def punjab_critical(client):
    """A CRITICAL Punjab work (SNO route target = Punjab)."""
    resp = client.get("/api/projects", params={"tier": "CRITICAL", "page_size": 1})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items, "No CRITICAL projects found"
    return items[0]


class TestCreateAndRoute:
    def test_report_to_mp_routes_to_works_mp(self, client, punjab_critical):
        payload = {
            "project_id": punjab_critical["project_id"],
            "reported_by_role": "MoSPI Audit Cell",
            "target_role": "MP",
            "comment": "Test: please review this flagged work",
        }
        resp = client.post("/api/reports", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "NEW"
        assert body["mp_name"] == punjab_critical["mp_name"]
        assert body["state"] == punjab_critical["state"]
        assert body["risk_category"] == "CRITICAL"
        assert 0 <= body["risk_score_display"] <= 100
        assert body["comment"] == "Test: please review this flagged work"

    def test_report_to_sno_routes_to_works_state(self, client, punjab_critical):
        resp = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "State Nodal Officer",
                "comment": None,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == punjab_critical["state"]

    def test_unknown_project_404(self, client):
        resp = client.post(
            "/api/reports",
            json={
                "project_id": "999999|Nobody|Nowhere|Nowhere-State",
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
            },
        )
        assert resp.status_code == 404

    def test_unknown_target_role_422(self, client, punjab_critical):
        resp = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "Prime Minister",
            },
        )
        assert resp.status_code == 422


class TestInboxVisibility:
    def test_mp_sees_own_report(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        resp = client.get("/api/reports", params={"role": "mp", "mp": mp_name})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert any(r["project_id"] == punjab_critical["project_id"] for r in body["items"])

    def test_other_mp_does_not_see_it(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        resp = client.get(
            "/api/reports", params={"role": "mp", "mp": mp_name + " XX"}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_sno_sees_state_report(self, client, punjab_critical):
        resp = client.get(
            "/api/reports", params={"role": "sno", "state": punjab_critical["state"]}
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_mospi_inbox_visible(self, client, punjab_critical):
        client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MoSPI Audit Cell",
                "comment": "Central review copy",
            },
        )
        resp = client.get("/api/reports", params={"role": "mospi"})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_inbox_requires_scope(self, client):
        resp = client.get("/api/reports", params={"role": "mp"})
        assert resp.status_code == 422
        resp = client.get("/api/reports", params={"role": "sno"})
        assert resp.status_code == 422

    def test_unknown_viewer_role_422(self, client):
        resp = client.get("/api/reports", params={"role": "minister"})
        assert resp.status_code == 422


class TestAck:
    def test_target_can_ack_own_report(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
                "comment": "ack test",
            },
        ).json()
        resp = client.post(
            f"/api/reports/{created['id']}/ack", params={"role": "mp", "mp": mp_name}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACKNOWLEDGED"

        inbox = client.get("/api/reports", params={"role": "mp", "mp": mp_name}).json()
        mine = [r for r in inbox["items"] if r["id"] == created["id"]]
        assert mine and mine[0]["status"] == "ACKNOWLEDGED"

    def test_cannot_ack_someone_elses_report(self, client, punjab_critical):
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
            },
        ).json()
        resp = client.post(
            f"/api/reports/{created['id']}/ack",
            params={"role": "mp", "mp": punjab_critical["mp_name"] + " XX"},
        )
        assert resp.status_code == 404

    def test_status_filter(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        resp = client.get(
            "/api/reports", params={"role": "mp", "mp": mp_name, "status": "NEW"}
        )
        assert resp.status_code == 200
        assert all(r["status"] == "NEW" for r in resp.json()["items"])


class TestClear:
    def test_clear_only_own_inbox(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        # Two reports for the target MP, one for the state SNO
        client.post("/api/reports", json={"project_id": punjab_critical["project_id"], "reported_by_role": "MoSPI Audit Cell", "target_role": "MP"})
        client.post("/api/reports", json={"project_id": punjab_critical["project_id"], "reported_by_role": "MoSPI Audit Cell", "target_role": "State Nodal Officer"})

        resp = client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})
        assert resp.status_code == 200
        deleted = resp.json()["deleted"]
        assert deleted >= 2

        # MP inbox empty now...
        inbox = client.get("/api/reports", params={"role": "mp", "mp": mp_name}).json()
        assert inbox["total"] == 0
        # ...but the SNO report survived (scope isolation applies to clear too)
        sno = client.get("/api/reports", params={"role": "sno", "state": punjab_critical["state"]}).json()
        assert sno["total"] >= 1
        # Cleanup for later tests: clear the SNO inbox too
        client.post("/api/reports/clear", params={"role": "sno", "state": punjab_critical["state"]})

    def test_clear_requires_scope(self, client):
        resp = client.post("/api/reports/clear", params={"role": "mp"})
        assert resp.status_code == 422

    def test_clear_other_mp_leaves_own_intact(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        client.post("/api/reports", json={"project_id": punjab_critical["project_id"], "reported_by_role": "MoSPI Audit Cell", "target_role": "MP"})
        client.post("/api/reports/clear", params={"role": "mp", "mp": "Someone Else"})
        inbox = client.get("/api/reports", params={"role": "mp", "mp": mp_name}).json()
        assert inbox["total"] == 1
        # Cleanup
        client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})


class TestSummaryMd:
    """D-031 Step 1: analysis snapshot attached to a report (backward-compatible)."""

    SUMMARY = (
        "RISK SNAPSHOT — Work 80673 (CRITICAL, 90/100)\n"
        "Signals: ghost/stalled pattern (86), cost outlier (71)\n"
        "Financials: ₹1.24 Cr recommended · ₹0 expenditure\n"
        "Indicators for review — not findings."
    )

    def test_create_with_summary_roundtrips_through_inbox(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
                "comment": "see attached snapshot",
                "summary_md": self.SUMMARY,
            },
        ).json()
        assert created["summary_md"] == self.SUMMARY

        inbox = client.get("/api/reports", params={"role": "mp", "mp": mp_name}).json()
        mine = [r for r in inbox["items"] if r["id"] == created["id"]]
        assert mine and mine[0]["summary_md"] == self.SUMMARY
        # Cleanup
        client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})

    def test_summary_without_field_still_works(self, client, punjab_critical):
        """Backward compatibility: old callers send no summary_md."""
        mp_name = punjab_critical["mp_name"]
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
            },
        ).json()
        assert created["summary_md"] is None
        client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})

    def test_summary_over_4000_chars_422(self, client, punjab_critical):
        resp = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
                "summary_md": "x" * 4001,
            },
        )
        assert resp.status_code == 422

    def test_summary_endpoint_scope_isolation(self, client, punjab_critical):
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
                "summary_md": self.SUMMARY,
            },
        ).json()
        # Target reads it back
        ok = client.get(
            f"/api/reports/{created['id']}/summary",
            params={"role": "mp", "mp": punjab_critical["mp_name"]},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["summary_md"] == self.SUMMARY
        assert body["status"] == "NEW"
        # A different MP cannot
        other = client.get(
            f"/api/reports/{created['id']}/summary",
            params={"role": "mp", "mp": punjab_critical["mp_name"] + " XX"},
        )
        assert other.status_code == 404
        # Cleanup
        client.post("/api/reports/clear", params={"role": "mp", "mp": punjab_critical["mp_name"]})

    def test_summary_endpoint_404_for_unknown_id(self, client):
        resp = client.get(
            "/api/reports/999999/summary", params={"role": "mospi"}
        )
        assert resp.status_code == 404

    def test_ack_sets_timestamp_and_summary_view_reflects_it(self, client, punjab_critical):
        mp_name = punjab_critical["mp_name"]
        created = client.post(
            "/api/reports",
            json={
                "project_id": punjab_critical["project_id"],
                "reported_by_role": "MoSPI Audit Cell",
                "target_role": "MP",
                "summary_md": self.SUMMARY,
            },
        ).json()
        client.post(
            f"/api/reports/{created['id']}/ack", params={"role": "mp", "mp": mp_name}
        )
        view = client.get(
            f"/api/reports/{created['id']}/summary",
            params={"role": "mp", "mp": mp_name},
        ).json()
        assert view["status"] == "ACKNOWLEDGED"
        assert view["acknowledged_at"] is not None
        # Cleanup
        client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})

    def test_summary_json_roundtrip_and_invalid_json_falls_back(self, client, punjab_critical):
        """Structured snapshot (D-031 Step-1 follow-up): stored verbatim,
        served verbatim; the inbox renders rich UI only when it parses."""
        mp_name = punjab_critical["mp_name"]
        payload = {
            "project_id": punjab_critical["project_id"],
            "reported_by_role": "MoSPI Audit Cell",
            "target_role": "MP",
            "summary_json": '{"why_flagged":["Ghost/stalled pattern"],"flagged_engines":[{"engine":"Rules & Compliance","score":86}],"financials":{"recommended":"\u20b91.24 Cr"}}',
        }
        created = client.post("/api/reports", json=payload).json()
        assert "summary_json" in created
        inbox = client.get("/api/reports", params={"role": "mp", "mp": mp_name}).json()
        mine = [r for r in inbox["items"] if r["id"] == created["id"]]
        assert mine and mine[0]["summary_json"] == payload["summary_json"]
        client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})


class TestProjectHistory:
    """D-031 Step 3: GET /api/reports/history/{project_id} — the dossier trail."""

    def test_history_empty_for_unreported_work(self, client, punjab_critical):
        resp = client.get(f"/api/reports/history/{punjab_critical['project_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_category"] == "CRITICAL"
        assert body["risk_score_display"] >= 0
        # Nothing reported to this MP yet (earlier tests clean up after themselves)
        assert isinstance(body["events"], list)

    def test_history_lists_events_newest_first(self, client, punjab_critical):
        pid = punjab_critical["project_id"]
        mp_name = punjab_critical["mp_name"]
        a = client.post("/api/reports", json={"project_id": pid, "reported_by_role": "MoSPI Audit Cell", "target_role": "MP"}).json()
        b = client.post("/api/reports", json={"project_id": pid, "reported_by_role": "State Nodal Officer", "target_role": "MoSPI Audit Cell", "comment": "escalation"}).json()
        try:
            body = client.get(f"/api/reports/history/{pid}").json()
            assert body["total_reports"] >= 2
            ids = [e["id"] for e in body["events"]]
            assert ids.index(b["id"]) < ids.index(a["id"])  # newest first
            assert body["new_reports"] >= 2
            assert any(e["comment"] == "escalation" for e in body["events"])
        finally:
            client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})
            client.post("/api/reports/clear", params={"role": "mospi"})

    def test_history_shows_ack_status_and_timestamp(self, client, punjab_critical):
        pid = punjab_critical["project_id"]
        mp_name = punjab_critical["mp_name"]
        created = client.post("/api/reports", json={"project_id": pid, "reported_by_role": "MoSPI Audit Cell", "target_role": "MP"}).json()
        try:
            client.post(f"/api/reports/{created['id']}/ack", params={"role": "mp", "mp": mp_name})
            body = client.get(f"/api/reports/history/{pid}").json()
            ev = [e for e in body["events"] if e["id"] == created["id"]][0]
            assert ev["status"] == "ACKNOWLEDGED"
            assert ev["acknowledged_at"] is not None
        finally:
            client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})

    def test_history_snapshot_flag(self, client, punjab_critical):
        pid = punjab_critical["project_id"]
        mp_name = punjab_critical["mp_name"]
        client.post("/api/reports", json={"project_id": pid, "reported_by_role": "MoSPI Audit Cell", "target_role": "MP", "summary_md": "snap"})
        created2 = client.post("/api/reports", json={"project_id": pid, "reported_by_role": "MoSPI Audit Cell", "target_role": "MP"}).json()
        try:
            body = client.get(f"/api/reports/history/{pid}").json()
            by_id = {e["id"]: e for e in body["events"]}
            assert any(e["has_snapshot"] for e in body["events"])
            assert by_id[created2["id"]]["has_snapshot"] is False
        finally:
            client.post("/api/reports/clear", params={"role": "mp", "mp": mp_name})

    def test_history_unknown_project_404(self, client):
        resp = client.get("/api/reports/history/999999|Nobody|Nowhere|Nowhere-State")
        assert resp.status_code == 404
