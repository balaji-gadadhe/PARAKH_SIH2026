"""
test_citizen.py
===============
Tests for the Citizen Participation Portal backend — D-032.

Covers: demo Aadhaar+OTP login, one-vote-per-citizen (server-enforced toggle),
feed ordering/filters, citizen reports (criteria validation, image upload,
location sanity wording), PSI, overview, and seed determinism.

Uses a temp SQLite db + temp uploads dir via PARAKH_CITIZEN_DB /
PARAKH_UPLOAD_DIR so the runtime backend/citizen.db and backend/uploads/
are never touched.

Run from repo root:
    python -m pytest backend/tests/test_citizen.py -v
"""

from __future__ import annotations

import io
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
    """TestClient + temp citizen db + temp uploads dir for this module."""
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PARAKH_CITIZEN_DB"] = str(Path(tmp) / "test_citizen.db")
        os.environ["PARAKH_UPLOAD_DIR"] = str(Path(tmp) / "uploads")
        with TestClient(app) as c:
            yield c
        os.environ.pop("PARAKH_CITIZEN_DB", None)
        os.environ.pop("PARAKH_UPLOAD_DIR", None)


@pytest.fixture(scope="module")
def critical_work(client):
    resp = client.get("/api/projects", params={"tier": "CRITICAL", "page_size": 1})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items, "No CRITICAL projects found"
    return items[0]


@pytest.fixture(scope="module")
def citizen(client):
    """A logged-in demo citizen + a dedicated toggle-test work (low-risk, so
    seed interference is nil and vote toggles never touch the demo headline
    critical work)."""
    resp = client.post("/api/citizen/login", json={"aadhaar": "111122223333", "otp": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    feed = client.get("/api/citizen/feed", params={"tier": "LOW", "sort": "risk_asc", "page_size": 1}).json()
    body["toggle_pid"] = feed["items"][0]["project_id"]
    return body


@pytest.fixture(scope="module")
def other_citizen(client):
    resp = client.post("/api/citizen/login", json={"aadhaar": "999988887777", "otp": "654321"})
    assert resp.status_code == 200
    return resp.json()


# ─── Login ────────────────────────────────────────────────────────────────────


class TestLogin:
    def test_login_returns_token_and_masked_id(self, citizen):
        assert citizen["token"].startswith("demo-citizen-")
        assert citizen["masked_id"].startswith("CIT-")
        assert "UIDAI" in citizen["demo_notice"] or "simulated" in citizen["demo_notice"].lower()

    def test_second_login_same_id_is_not_new(self, client):
        r1 = client.post("/api/citizen/login", json={"aadhaar": "111122223333", "otp": "123456"})
        r2 = client.post("/api/citizen/login", json={"aadhaar": "111122223333", "otp": "999999"})
        assert r1.status_code == r2.status_code == 200
        assert r1.json()["is_new"] is False
        assert r2.json()["is_new"] is False

    def test_login_rejects_short_aadhaar(self, client):
        resp = client.post("/api/citizen/login", json={"aadhaar": "123", "otp": "123456"})
        assert resp.status_code == 422

    def test_login_rejects_non_digit_aadhaar(self, client):
        resp = client.post("/api/citizen/login", json={"aadhaar": "abcd1234efgh", "otp": "123456"})
        assert resp.status_code == 422

    def test_login_rejects_bad_otp_length(self, client):
        resp = client.post("/api/citizen/login", json={"aadhaar": "111122223333", "otp": "12"})
        assert resp.status_code == 422


# ─── Me ───────────────────────────────────────────────────────────────────────


class TestMe:
    def test_me_counts_activity(self, client, citizen, critical_work):
        token = citizen["token"]
        client.post("/api/citizen/vote", json={"token": token, "project_id": critical_work["project_id"]})
        resp = client.get("/api/citizen/me", params={"token": token})
        assert resp.status_code == 200
        body = resp.json()
        assert body["upvotes_cast"] >= 1
        assert body["masked_id"].startswith("CIT-")
        assert body["masked_id"] == citizen["masked_id"]

    def test_me_rejects_unknown_token(self, client):
        resp = client.get("/api/citizen/me", params={"token": "demo-citizen-000000000000"})
        assert resp.status_code == 401


# ─── Votes ────────────────────────────────────────────────────────────────────


class TestVotes:
    def test_vote_then_unvote_toggle(self, client, citizen, critical_work):
        """Reddit-style toggle: a full vote→unvote→vote cycle returns the count
        to its starting value with alternating `voted` flags — deterministic
        regardless of prior state (order-independent tests)."""
        token = citizen["token"]
        pid = citizen["toggle_pid"]
        r1 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()
        r2 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()
        r3 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()
        assert r2["voted"] is (not r1["voted"])
        assert r3["voted"] == r1["voted"]
        assert r3["upvote_count"] == r1["upvote_count"]  # cycle restores exactly

    def test_double_vote_is_impossible(self, client, citizen, critical_work):
        """THE anti-spam guarantee: 3 rapid votes from one citizen = net 0
        (toggle + UNIQUE constraint) — the count can never inflate."""
        token = citizen["token"]
        pid = citizen["toggle_pid"]
        c1 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()["upvote_count"]
        c2 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()["upvote_count"]
        c3 = client.post("/api/citizen/vote", json={"token": token, "project_id": pid}).json()["upvote_count"]
        assert abs(c1 - c2) == 1
        assert c3 == c1  # net effect of 3 votes = zero, never +3

    def test_votes_are_independent_per_citizen(self, client, citizen, other_citizen, critical_work):
        """Two citizens voting on the same work — counts add up independently."""
        pid = citizen["toggle_pid"]
        r1 = client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid}).json()
        r2 = client.post("/api/citizen/vote", json={"token": other_citizen["token"], "project_id": pid}).json()
        assert r2["upvote_count"] == r1["upvote_count"] + 1
        # clean up: both un-vote (toggle)
        client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid})
        client.post("/api/citizen/vote", json={"token": other_citizen["token"], "project_id": pid})

    def test_vote_unknown_project_404(self, client, citizen):
        resp = client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": "NOPE-123"})
        assert resp.status_code == 404

    def test_vote_bad_token_401(self, client, critical_work):
        resp = client.post("/api/citizen/vote", json={"token": "garbage", "project_id": critical_work["project_id"]})
        assert resp.status_code == 401


# ─── Feed ─────────────────────────────────────────────────────────────────────


class TestFeed:
    def test_feed_default_sort_upvotes_desc(self, client):
        resp = client.get("/api/citizen/feed", params={"page_size": 20})
        assert resp.status_code == 200
        body = resp.json()
        assert body["demo_seed"] is True
        counts = [i["upvote_count"] for i in body["items"]]
        assert counts == sorted(counts, reverse=True)

    def test_feed_sorts_before_pagination(self, client):
        """Regression: page 1 of the default sort must contain the globally
        most-upvoted works, not merely the first N rows re-ordered locally."""
        top = client.get("/api/citizen/feed", params={"page_size": 5}).json()["items"]
        assert top, "feed must not be empty"
        best = top[0]["upvote_count"]
        assert best > 0, "seed guarantees engagement on the top-flagged works"
        # Every other work on page 1 must have ≤ the top item's votes, and the
        # overall max must sit on page 1 (nothing more-upvoted hides on page 2+).
        assert all(i["upvote_count"] <= best for i in top)
        page2 = client.get("/api/citizen/feed", params={"page": 2, "page_size": 5}).json()["items"]
        if page2:
            assert max(i["upvote_count"] for i in page2) <= best

    def test_feed_risk_sort(self, client):
        resp = client.get("/api/citizen/feed", params={"sort": "risk_desc", "page_size": 20})
        scores = [i["risk_score_display"] for i in resp.json()["items"]]
        assert scores == sorted(scores, reverse=True)

    def test_feed_tier_filter(self, client):
        resp = client.get("/api/citizen/feed", params={"tier": "CRITICAL", "page_size": 50})
        assert all(i["risk_category"] == "CRITICAL" for i in resp.json()["items"])

    def test_feed_search(self, client, critical_work):
        resp = client.get("/api/citizen/feed", params={"q": critical_work["project_id"], "page_size": 10})
        items = resp.json()["items"]
        assert items and items[0]["project_id"] == critical_work["project_id"]

    def test_feed_voted_flag_matches_vote_state(self, client, citizen, critical_work):
        """The feed's per-citizen `voted` flag always mirrors the vote state —
        whatever the toggle left behind."""
        pid = critical_work["project_id"]
        vote = client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid}).json()
        resp = client.get("/api/citizen/feed", params={"token": citizen["token"], "q": pid})
        items = resp.json()["items"]
        assert items and items[0]["project_id"] == pid
        assert items[0]["voted"] is vote["voted"]

    def test_feed_pagination(self, client):
        r1 = client.get("/api/citizen/feed", params={"page": 1, "page_size": 5})
        r2 = client.get("/api/citizen/feed", params={"page": 2, "page_size": 5})
        ids1 = {i["project_id"] for i in r1.json()["items"]}
        ids2 = {i["project_id"] for i in r2.json()["items"]}
        assert not (ids1 & ids2), "pages must not overlap"


# ─── Reports ──────────────────────────────────────────────────────────────────


class TestCitizenReports:
    def test_report_basic(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "stalled,quality",
                "comment": "No progress visible at the site for months.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["criteria"] == ["stalled", "quality"]
        assert body["verification_status"] == "UNVERIFIED"
        assert body["is_seed"] is False
        assert body["risk_category"] == critical_work["risk_category"]

    def test_report_unknown_criteria_422(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "banana",
            },
        )
        assert resp.status_code == 422

    def test_report_empty_criteria_422(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={"token": citizen["token"], "project_id": critical_work["project_id"], "criteria": " , "},
        )
        assert resp.status_code == 422

    def test_report_unknown_project_404(self, client, citizen):
        resp = client.post(
            "/api/citizen/reports",
            data={"token": citizen["token"], "project_id": "NOPE-123", "criteria": "stalled"},
        )
        assert resp.status_code == 404

    def test_report_bad_token_401(self, client, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={"token": "nope", "project_id": critical_work["project_id"], "criteria": "stalled"},
        )
        assert resp.status_code == 401

    def test_report_with_image_upload(self, client, citizen, critical_work):
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c626001000000ffff03000006000557bfabd40000000049454e44ae426082"
        )
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "quality",
            },
            files={"image": ("site.png", io.BytesIO(png), "image/png")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_image"] is True
        assert body["image_url"] and body["image_url"].startswith("/api/citizen/uploads/")
        # The served image must actually resolve
        img = client.get(body["image_url"])
        assert img.status_code == 200

    def test_report_rejects_bad_image_type(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "quality",
            },
            files={"image": ("evil.exe", io.BytesIO(b"MZ..."), "application/octet-stream")},
        )
        assert resp.status_code == 422

    def test_report_location_sanity_plausible(self, client, citizen, critical_work):
        """Punjab work + coords inside Punjab's coarse bbox → PLAUSIBLE."""
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "stalled",
                "latitude": "30.9",
                "longitude": "75.8",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["location_sanity"] == "PLAUSIBLE"

    def test_report_location_sanity_far(self, client, citizen, critical_work):
        """Punjab work + Kerala coords → FAR_FROM_CLAIMED_STATE (still UNVERIFIED)."""
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "criteria": "stalled",
                "latitude": "9.9",
                "longitude": "76.2",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["location_sanity"] == "FAR_FROM_CLAIMED_STATE"
        assert body["verification_status"] == "UNVERIFIED"

    def test_report_without_location(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={"token": citizen["token"], "project_id": critical_work["project_id"], "criteria": "other"},
        )
        assert resp.json()["location_sanity"] == "NO_LOCATION"

    def test_pure_satisfaction_feedback(self, client, citizen, critical_work):
        """No criteria, just a 1–5 rating — the feedback flavor of reporting."""
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "satisfaction": "2",
                "comment": "Dissatisfied with the pace of work.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["criteria"] == []
        assert body["satisfaction"] == 2
        assert body["verification_status"] == "UNVERIFIED"

    def test_satisfaction_without_either_422(self, client, citizen, critical_work):
        """No criteria AND no rating = nothing to store."""
        resp = client.post(
            "/api/citizen/reports",
            data={"token": citizen["token"], "project_id": critical_work["project_id"]},
        )
        assert resp.status_code == 422

    def test_satisfaction_out_of_range_422(self, client, citizen, critical_work):
        resp = client.post(
            "/api/citizen/reports",
            data={
                "token": citizen["token"],
                "project_id": critical_work["project_id"],
                "satisfaction": "9",
            },
        )
        assert resp.status_code == 422

    def test_reports_list_public(self, client, critical_work):
        resp = client.get("/api/citizen/reports", params={"project_id": critical_work["project_id"]})
        assert resp.status_code == 200
        assert resp.json()["demo_seed"] is True
        assert len(resp.json()["items"]) >= 1


# ─── PSI ──────────────────────────────────────────────────────────────────────


class TestPsi:
    def test_psi_for_seeded_critical_work(self, client, critical_work):
        """Top-risk works have seed activity → PSI > 0, HIGH-ish."""
        resp = client.get(f"/api/citizen/psi/{critical_work['project_id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["upvote_count"] >= 0
        assert 0 <= body["psi_score"] <= 100
        assert body["label"] in ("NO_SIGNAL", "LOW", "MODERATE", "HIGH")
        assert "NOT a detection engine" in body["disclaimer"]

    def test_vote_reasons_flow_into_psi_breakdown(self, client, citizen):
        """Upvote 'why' tags and report criteria share one vocabulary — both
        surface in the PSI reasons breakdown (the citizen-signal story).
        Uses a HIGH work this citizen never voted on: no toggle parity issues
        (seed citizens are distinct, so a first POST always inserts)."""
        resp = client.get("/api/citizen/feed", params={"tier": "HIGH", "sort": "risk_desc", "page_size": 1})
        pid = resp.json()["items"][0]["project_id"]
        r = client.post(
            "/api/citizen/vote",
            json={"token": citizen["token"], "project_id": pid, "reasons": ["stalled", "cost"]},
        )
        assert r.status_code == 200
        assert r.json()["voted"] is True
        psi = client.get(f"/api/citizen/psi/{pid}").json()
        reasons = {d["reason"]: d["count"] for d in psi["reasons_breakdown"]}
        assert reasons.get("stalled", 0) >= 1
        assert reasons.get("cost", 0) >= 1
        # cleanup (toggle off — leaves the work as we found it)
        client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid})

    def test_psi_satisfaction_aggregation(self, client, citizen, critical_work):
        """Satisfaction ratings aggregate to a 1–5 average in the PSI."""
        pid = critical_work["project_id"]
        client.post(
            "/api/citizen/reports",
            data={"token": citizen["token"], "project_id": pid, "satisfaction": "1"},
        )
        psi = client.get(f"/api/citizen/psi/{pid}").json()
        assert psi["satisfaction_count"] >= 1
        assert psi["satisfaction_avg"] is not None
        assert 1 <= psi["satisfaction_avg"] <= 5

    def test_psi_unknown_project_404(self, client):
        resp = client.get("/api/citizen/psi/NOPE-123")
        assert resp.status_code == 404

    def test_psi_reflects_a_new_vote(self, client, citizen, critical_work):
        """A quiet LOW-tier work: vote → PSI moves by exactly +1 (transparent)."""
        resp = client.get("/api/citizen/feed", params={"tier": "LOW", "sort": "risk_asc", "page_size": 5})
        pid = resp.json()["items"][-1]["project_id"]  # 5th pick ≠ fixture's toggle work
        before = client.get(f"/api/citizen/psi/{pid}").json()
        client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid})
        after = client.get(f"/api/citizen/psi/{pid}").json()
        assert after["psi_score"] == before["psi_score"] + 1
        client.post("/api/citizen/vote", json={"token": citizen["token"], "project_id": pid})  # cleanup toggle


# ─── Overview ─────────────────────────────────────────────────────────────────


class TestOverview:
    def test_overview_shape_and_seed_label(self, client):
        resp = client.get("/api/citizen/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["demo_seed"] is True
        assert body["total_citizens"] > 0
        assert body["total_upvotes"] > 0
        assert body["total_reports"] > 0
        assert body["works_engaged"] > 0
        assert isinstance(body["top_upvoted"], list) and body["top_upvoted"]
        assert isinstance(body["recent_reports"], list)
        assert isinstance(body["by_state"], list)

    def test_overview_top_upvoted_sorted(self, client):
        body = client.get("/api/citizen/overview").json()
        counts = [i["upvote_count"] for i in body["top_upvoted"]]
        assert counts == sorted(counts, reverse=True)


class TestFacets:
    """The 'near me' filter index (D-032): real states/constituencies/MPs."""

    def test_facets_shape(self, client):
        resp = client.get("/api/citizen/facets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_states"] > 20
        assert body["total_constituencies"] > body["total_states"]
        assert len(body["states"]) == body["total_states"]

    def test_facets_cascade_is_honored_by_feed(self, client):
        """Every (state → constituency) pair the dropdown offers must actually
        return results from /feed — the dropdown can never lie."""
        body = client.get("/api/citizen/facets").json()
        # Spot-check three states (full cascade would be 500+ feed calls)
        checked = 0
        for st in body["states"]:
            if checked >= 3:
                break
            if not st["constituencies"]:
                continue
            const = st["constituencies"][0]
            resp = client.get(
                "/api/citizen/feed",
                params={"state": st["state"], "constituency": const, "page_size": 5},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] > 0, f"{st['state']} → {const} returned 0 works"
            for item in data["items"]:
                assert st["state"].lower() in item["state"].lower()
                assert const.lower() in item["constituency"].lower()
            checked += 1
        assert checked == 3

    def test_feed_top_concerns_combine_votes_and_reports(self, client, citizen, critical_work):
        """THE shared-signal rule: an upvote-with-reason adds to the same
        per-reason counter as a report-criteria; the feed shows the combined
        total as top_concerns."""
        token = citizen["token"]
        pid = critical_work["project_id"]
        # Baseline combined count for 'quality' on this work.
        before = client.get("/api/citizen/feed", params={"q": pid.split("|")[0]}).json()
        item = next((i for i in before["items"] if i["project_id"] == pid), None)
        assert item is not None
        base = next(
            (c["count"] for c in item["top_concerns"] if c["reason"] == "quality"), 0
        )
        # Upvote with the 'quality' reason.
        r = client.post(
            "/api/citizen/vote", json={"token": token, "project_id": pid, "reasons": ["quality"]}
        )
        assert r.status_code == 200
        # Feed must reflect +1 on that reason (combined tally).
        after = client.get("/api/citizen/feed", params={"q": pid.split("|")[0]}).json()
        item2 = next(i for i in after["items"] if i["project_id"] == pid)
        got = next(
            (c["count"] for c in item2["top_concerns"] if c["reason"] == "quality"), 0
        )
        assert got == base + 1

    def test_facets_states_ordered_by_attention(self, client):
        body = client.get("/api/citizen/facets").json()
        states = [s["state"] for s in body["states"]]
        assert len(states) == len(set(states))  # no duplicates
        # Constituency + MP lists sorted (stable dropdown UX)
        for st in body["states"][:5]:
            assert st["constituencies"] == sorted(st["constituencies"])
            assert st["mps"] == sorted(st["mps"])


# ─── Seed determinism ─────────────────────────────────────────────────────────


class TestSeed:
    def test_seed_is_flagged_synthetic(self, client, critical_work):
        resp = client.get("/api/citizen/reports", params={"project_id": critical_work["project_id"]})
        for item in resp.json()["items"]:
            if item["masked_id"] == "CIT-SEED (synthetic)":
                assert item["is_seed"] is True

    def test_seed_deterministic_across_dbs(self, critical_work):
        """Two fresh dbs, both seeded → identical participation numbers (D-027 spirit)."""
        from backend.app.routers.citizen import _ensure_seeded, _vote_counts, _report_counts

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PARAKH_CITIZEN_DB"] = str(Path(tmp) / "a.db")
            _ensure_seeded()  # trigger the seed on db A
            counts_a = (dict(_vote_counts()), dict(_report_counts()))
            os.environ["PARAKH_CITIZEN_DB"] = str(Path(tmp) / "b.db")
            _ensure_seeded()  # trigger the seed on db B
            counts_b = (dict(_vote_counts()), dict(_report_counts()))
        os.environ.pop("PARAKH_CITIZEN_DB", None)
        assert counts_a == counts_b, "seed must be deterministic"
        pid = critical_work["project_id"]
        assert counts_a[0].get(pid, 0) > 0, "top critical work must carry seed votes"

    def test_seed_runs_only_once_per_db(self, client):
        """Calling the endpoints repeatedly must not grow the seed."""
        body1 = client.get("/api/citizen/overview").json()
        body2 = client.get("/api/citizen/overview").json()
        assert body1["total_upvotes"] == body2["total_upvotes"]
        assert body1["total_reports"] == body2["total_reports"]
