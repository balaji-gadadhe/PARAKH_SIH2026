# ml_features — Detection Engines & Risk Layer

ML/analytics package for PARAKH: feature inputs (`ml_input/`), engine modules (`analytics/`), dataset runners (`scripts/`), generated outputs (`ml_outputs/` — demo-critical files committed per D-027, the rest gitignored & regenerable), tests (`tests/`).

## Run tests

```bash
cd ml_features
python -m pytest tests -q        # 69 passed
```

## Engine runners (full dataset — deterministic, re-runs are byte-identical)

```bash
python scripts/run_rule_engine_on_dataset.py          # 86,976 projects → ml_outputs/rules/
python scripts/run_similarity_engine_on_dataset.py    # 50k pairs (~140 s) → ml_outputs/similarity/
python scripts/run_feature_integration.py             # → project_risk_results.csv (the risk layer)
python scripts/run_early_warning_pipeline.py          # trends + alerts + vendor wiring (post-processing)
```

Direct model runs (also save `.joblib` to `analytics/ml_engine/train/model_registry/`):

```bash
python analytics/ml_engine/cost_anomaly_model.py
python analytics/ml_engine/isolation_forest_model.py
python analytics/ml_engine/xgboost_delay_model.py
```

Inspect results interactively:

```bash
python scripts/inspect_project_risk.py --tier CRITICAL --limit 5
python scripts/inspect_project_risk.py --compare     # 2 flagged vs 2 clean projects
python scripts/run_rule_engine_on_dataset.py --rule_id GHOST-002 --limit 10
```

## Engines (`analytics/`)

| Module | What it does |
|---|---|
| `rule_engine/` | Deterministic rules: COMPLIANCE-001..008, GHOST-001..004 (stalled/ghost), PROGRESS-001..004, threshold helpers. Safe against missing data — unavailable fields never trigger rules. |
| `ml_engine/` | IsolationForest (multivariate anomaly), XGBoost (delay prediction from completed works), cost anomaly (LOF + peer statistics + typology classification). |
| `payment_anomaly/` | Round-figure extraction, payment frequency/velocity/structuring, budget overruns + large payments. Weighted fusion of domain indicators + IsolationForest score. |
| `agency_profiling/` | Vendor profiles from historical performance; risk score 0–100 with **empirical credibility shrinkage** for small-sample vendors; human-readable risk reasons. |
| `similarity_engine/` | TF-IDF duplicate detection (generic-template filter, geo relationship classification, cost-ratio annotation) → per-project duplicate risk. Location = synthetic demo only; image hashing = stub (deferred). |
| `feature_integration/` | **The risk layer** — see below. |
| `early_warning/` | Burn-rate trends (RUNAWAY/STALLED/ACCELERATED/NEW/NORMAL) + 5 alert codes. Wired via `run_early_warning_pipeline.py` (D-020). |
| `explainability/` | Reason generator (plain-English factors) + a TreeSHAP explainer for the delay model. **Note:** the `shap` package is not currently installed or run in the demo pipeline — the explainer's output is not part of the shipped demo data (see `progress.md` stretch queue for the planned activation). |
| `investigation/` | `InvestigationPrioritizer` (60% risk + 40% log-exposure → priority 0–100, TIER_1..4) + case ranking. Shared with the backend (D-021). |

## Feature Integration & Aggregate Risk pipeline

Merges every engine's output into one evidence-ready table — **strict 1 row = 1 project** (cardinality enforced, row explosions raise).

```text
Detection outputs → loaders & validators → 1:N aggregators (rule events, similarity pairs)
  → safe merger (left joins, collision-free) → risk signal builder (normalize to [0,1])
  → risk aggregator (weighted composite + XAI) → project_risk_results.csv
```

- **Weights** (`config/risk_weights.json`): cost/delay/payment/rules 0.20, similarity/iforest 0.10 — **dynamically re-normalized** over each project's available engines, so scores stay in [0,1] even with missing engines.
- **Buckets:** LOW 0–0.30 · MEDIUM 0.30–0.60 · HIGH 0.60–0.80 · CRITICAL 0.80–1.00.
- **XAI per project:** `top_risk_signals` (ranked, score + weight %), `risk_factors` (factual drivers), `audit_explanation` (plain English), `evidence_payload` (JSON audit trail: component scores + active weights).
- Verified on real data: 86,976 → 86,976 rows, distribution CRITICAL 24 · HIGH 158 · MEDIUM 13,781 · LOW 73,013.

Run with `--strict` to fail on any missing/optional feature file.

## Inputs & outputs

- **Inputs** (`ml_input/`): `project_features.csv` (primary, 86,976 × 30), `mp_features.csv`, `vendor_features.csv`, `project_similarity_data.csv`, `data_dictionary.xlsx`. Join key: `project_id` (composite — Work IDs repeat).
- **Outputs** (`ml_outputs/`): engine result CSVs, `rules/`, `similarity/`, `agency_profiles.csv`, `integrated_project_features.csv`, **`project_risk_results.csv`** (unified risk output, 86,976 × 35; committed as **`project_risk_results.csv.gz`** per D-027 — the canonical demo copy, don't delete), `integration_report.json`, early-warning alerts/trends. `agency_profiles.csv` + the `.gz` are committed (D-027); the rest gitignored — regenerate with the runners above.

**Rule of the repo:** outputs are *risk indicators* — wording is `potential anomaly / requires investigation`, never "confirmed fraud" (D-008).
