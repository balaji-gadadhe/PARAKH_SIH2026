# PARAKH Backend

FastAPI read-only API over the ML detection pipeline's risk results.
Serves the full frontend card contract (`docs/frontend_card_reference.md` + `docs/frontend-skeleton.md` §5). All card fields are served and tested against real data.

## Run

```bash
# from SIH-2026/ — all data ships with the repo (D-027), no regeneration needed
pip install -r requirements.txt

uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
# Swagger: http://127.0.0.1:8000/docs
```

Startup loads **5 CSVs into memory** (~3 s, read-only):
`project_risk_results.csv` (required — plain CSV if present, else the committed `project_risk_results.csv.gz`) · `master_works` · `master_mp_summary` · `agency_profiles` · `ml_input/project_features` (peer-cost/payment detail fields).

## Endpoints (9 read + 5 report + 8 citizen)

| Endpoint | Returns |
|---|---|
| `GET /` | API info + health |
| `GET /api/health` | Data load status |
| `GET /api/dashboard/summary` | National KPIs + tier distribution + top states/MPs |
| `GET /api/dashboard/states` | **Per-state risk aggregation (D-031)** — tier counts, funds, flagged MPs; sorted HIGH+CRITICAL desc. Powers the India map |
| `GET /api/projects` | Paginated, filterable project list |
| `GET /api/projects/{project_id}` | Full investigation view (see below) |
| `GET /api/mps` | MP summary list (searchable, sortable) |
| `GET /api/mps/{mp_name}` | MP detail + works + per-tier counts + avg/highest risk |
| `GET /api/alerts` | Ranked flagged works + signal aggregates (paginated) |
| `GET /api/agencies` (+`/{id}`) | Vendor/agency profiles |
| `POST /api/reports` | Report a work → routed to the responsible authority's inbox (D-029/D-031; optional `comment`, `summary_md`, `summary_json` ≤4000 chars each) |
| `GET /api/reports` | Inbox for the viewer's role+scope (`status`, pagination) |
| `GET /api/reports/history/{project_id}` | **Investigation history (D-031)** — every report on a work, newest first, status + ack timestamps + snapshot flag |
| `GET /api/reports/{id}/summary` | Attached snapshot + ack timestamps (target-authority scope only) |
| `POST /api/reports/{id}/ack` | Target-only acknowledge (sets `acknowledged_at`) |
| `POST /api/reports/clear` | Hard-delete the caller's own inbox rows (scope-isolated) |

### Citizen Participation Portal (D-032 — demo, labeled)

| Endpoint | Returns |
|---|---|
| `POST /api/citizen/login` | Demo Aadhaar + OTP (any 12-digit ID + any 6-digit OTP; **simulated, labeled** — token `demo-citizen-<id>`, masked display id) |
| `GET /api/citizen/me` | The citizen's activity summary (upvotes cast, reports filed) |
| `POST /api/citizen/vote` | Upvote/unupvote toggle — **one vote per citizen per work, UNIQUE-enforced in SQLite** (the anti-spam rule is real; the identity is demo) |
| `GET /api/citizen/feed` | Works + public upvote/report counts — filter (tier/state/constituency/mp/category), search, sort (`upvotes_desc` default · `signals_desc` combined-concern volume · `risk_desc` · `amount_desc` · `reports_desc`), pagination; optional token adds per-citizen `voted` flags; rows carry `top_concerns` (top-3 combined reasons — **upvote-whys + report-criteria tallied together**, the shared citizen signal) |
| `GET /api/citizen/facets` | Facet index for the "near me" filters: every state with its **real constituency + MP lists** (from the dataset — dropdowns can never offer an unhonorable pair), ordered most-flagged-first |
| `POST /api/citizen/reports` | File a citizen report (multipart): **either** ≥1 criteria (`stalled,quality,cost,ghost,other`) **or** a 1–5 `satisfaction` rating (pure feedback) + comment + optional image (JPEG/PNG/WebP ≤5 MB) + optional lat/lon. Everything stored **UNVERIFIED** |
| `GET /api/citizen/reports` | Recent citizen reports (public, `is_seed` marks synthetic seed rows) |
| `GET /api/citizen/psi/{project_id}` | **PSI** — participation/sentiment signal (NOT a detection engine, NOT part of the risk score); transparent demo formula; includes `reasons_breakdown` (upvote-whys + report-criteria tallied together, each entry split into `report_count`/`upvote_count` for honesty) and `satisfaction_avg`/`satisfaction_count` |
| `GET /api/citizen/overview` | Portal participation stats: citizens, upvotes, reports, engaged works, top-upvoted, recent reports, by-state |
| `GET /api/citizen/uploads/{file}` | Serve a citizen-uploaded demo image |

Citizen storage: SQLite `backend/citizen.db` (gitignored; `PARAKH_CITIZEN_DB` env override for tests) + `backend/uploads/` (gitignored; `PARAKH_UPLOAD_DIR`). First use seeds a **deterministic synthetic participation set** (42 citizens, 140 vote attempts → ~130 unique upvotes, 30 reports with 1–5 satisfaction ratings, all with concern reasons, on the top-flagged works — every laptop serves identical numbers, D-027 spirit; all seed rows flagged `is_seed`). Location sanity wording (`PLAUSIBLE` / `FAR_FROM_CLAIMED_STATE` / `NO_LOCATION` / `NO_REFERENCE`) is a coarse plausibility signal that never promotes anything to verified. Votes carry `reasons` (self-healing `ALTER TABLE` migrations — old dbs upgrade in place).

## Query params

**`/api/projects`** — `q` (searches project_id OR work description) · `tier` · `state` · `mp` · `house` · `category` · `status` (completed/ongoing) · `min_score` (0–100) · `sort` (`risk_desc` default, `risk_asc`, `amount_desc`) · `page` · `page_size` (≤200).

**`/api/mps`** — `q` · `state` · `house` · `sort` (`flagged_desc` default, `works_desc`, `utilization_desc`, `completion_desc`).

**`/api/alerts`** — `tier` (default HIGH+CRITICAL) · `type` (signal substring) · `state` · `mp` · `min_score` · `q` · `page`/`page_size` (tier counts + signal aggregates always cover the **full** filtered set).

**`/api/agencies`** — `q` · `risk_level` · `sort` (`risk_desc` default, `risk_asc`, `projects_desc`) · pagination.

## Project detail — investigation view

- **Identity:** `work_description`, `status` (master_works join)
- **Risk:** `audit_explanation`, `top_risk_signals`, `risk_factors`, `evidence_payload`, `engines[6]` (score/flag/available each)
- **Investigation:** `investigation_priority` (0–100), `investigation_urgency` (TIER_1..4), `audit_dispatch_recommended` — computed by the **shared** `InvestigationPrioritizer` (`ml_features/analytics/investigation/prioritization.py`), the single authoritative formula (D-021)
- **Financials:** `final_amount`, `cost_variation_pct`, `peer_median_cost`, `peer_mean_cost`, `peer_std_cost`, `cost_deviation_from_peer`
- **Payments:** counts, avg/max/min, frequency, `latest_payment_status`
- **Vendor:** `primary_vendor`, `vendor_risk_score/level`
- **Other:** days since recommendation / to completion, rating, `has_images`, `ida`, similarity score

Missing values return `null` — the frontend renders **"Not available"** (card reference §6).

## Tests

```bash
python -m pytest backend/tests -q   # 137 tests (core API · reports · citizen · dashboard crosstab)
```

Includes assertions against the card reference's worked examples, which reproduce exactly: MP "Shri Harbhajan Singh (2022-28)" → 120 works, tiers 6/0/31/83, avg 24.58, highest 89.84 · project 80673 → priority 87.86, TIER_1, 85 payments.

**Note:** all string filters use `regex=False` — MP names contain regex metacharacters like `(2022-28)`.

## Stack

FastAPI · Pandas (in-memory caching) · Pydantic v2 · Uvicorn. No DB — CSV-read by design (D-018); a future SQLite/Supabase migration is transparent to the frontend.
