# PARAKH — Project Anomaly & Risk Assessment Knowledge Hub

**Smart India Hackathon 2026 · Problem Statement 26102 · Team 110**
*An explainable, closed-loop oversight platform for the MPLAD Scheme.*

PARAKH turns the national MPLADS worklist — **86,976 works · 731 MPs · 28,123 implementing agencies** — into explainable, prioritized investigation cases for the Ministry, State Nodal Authorities, District Authorities and MPs, then closes the accountability loop: **detect → investigate → report → acknowledge**.

**Verified batch distribution:** 73,013 LOW · 13,781 MEDIUM · 158 HIGH · 24 CRITICAL.

---

## What it does

| Layer | Detail |
|---|---|
| **Data foundation** | Public MPLADS releases cleaned into a frozen, committed batch — identical numbers reproduce on every machine |
| **Six detection engines** | Statutory rules (compliance/ghost/stalled) · Isolation Forest · XGBoost delay risk · LOF + peer cost statistics · payment analytics · TF-IDF similarity (a signal to cross-check, never proof) |
| **Explainable score** | One 0–100 composite with dynamic weight re-normalization; the dossier draws the actual weighted arithmetic and verifies it reconstructs the served score |
| **Investigation priority** | Risk combined with financial exposure → TIER_1 recommendations, so audit hours go where exposure is highest |
| **Role dashboards** | Ministry (national + state risk map) · SNO (state rollup) · MP (constituency) · DM (labeled demo proxy) |
| **Accountability loop** | Structured report → scoped authority inbox with analysis snapshot → acknowledge → permanent dossier trail → PDF handoff |
| **Citizen portal** | Simulated Aadhaar+OTP login, one-vote-per-citizen enforced server-side, reason-mandated upvotes, satisfaction ratings, photo+location reports — all labeled **unverified by design** |

The citizen signal surfaces as a **Public Satisfaction Indicator** beside the engine evidence — never part of the risk score, never routed into authority inboxes. Convergence with engine flags prioritizes an audit; divergence flags the data pipeline itself.

## Quickstart

```bash
# backend (Python 3.12+)
python -m venv venv
source venv/Scripts/activate        # Windows Git Bash; Linux: source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000

# frontend (Node 18+)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 — the homepage shows the frozen national numbers.

## Verify the claims

```bash
pytest                                   # 221 tests (backend · engines · realtime)
python scripts/smoke_e2e.py              # 22-check end-to-end suite
python scripts/checklist_full.py         # 76-check browser walkthrough (needs both servers)
```

The frozen dataset ships in-repo (`data/master/`, `ml_features/ml_outputs/project_risk_results.csv.gz`) — every test reproduces identical numbers on any machine.

## Honesty policy (enforced in code and UI)

- The system says **risk indicator / potential anomaly / requires investigation** — never "confirmed fraud".
- The batch is **historical** and labeled so on every page; realtime replay is labeled **simulation**.
- Missing values render as **"Not available"** — never silently converted into a penalty.
- Citizen submissions are **unverified by design**; the Aadhaar/OTP login is a simulated demo flow.
- Flagship case (work 80673): sanctioned Rs 5 lakh vs. Rs 1.38 crore expenditure (27.68x), 85 payments in 963 days — score 90/100 CRITICAL, priority 87.86; the dossier shows the exact engine arithmetic behind it.

## Repository map

```
backend/       FastAPI service + reports/citizen routers (SQLite write paths)
frontend/      Next.js 16 App Router dashboard + citizen portal
ml_features/   Detection engines (rules, Isolation Forest, XGBoost, LOF, payments, similarity)
realtime/      Historical replay module (239,230 events, labeled simulation)
scripts/       Data pipeline (01–04) + smoke/checklist verification suites
data/          Frozen MPLADS batch (master CSVs, validation, location demo module)
```

## Stack

Python · pandas · scikit-learn · XGBoost · FastAPI · SQLite · Next.js 16 · TypeScript · Tailwind CSS · Recharts

---

*PARAKH does not replace human oversight — it helps human oversight start at the right work, with the right explanation, and a traceable action loop.*
