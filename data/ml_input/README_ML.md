# PARAKH ML Input Documentation

Handoff docs for the ML datasets produced by the data pipeline.

## Datasets

| Dataset | Rows | Purpose |
|---|---:|---|
| `project_features.csv` | 86,976 × 30 | **Primary ML dataset** — project-level financial, time, categorical features |
| `mp_features.csv` | 774 × 17 | MP/constituency monitoring features |
| `project_similarity_data.csv` | 86,910 × 7 | Normalized descriptions + TF-IDF similarity |
| `vendor_features.csv` | 28,123 × 8 | Vendor expenditure/payment profiling |
| `data_dictionary.xlsx` | — | Feature definitions and usage notes |

**Primary key:** `project_id` — composite of `work_id | mp | constituency | state`, because source Work IDs are **not globally unique**.

## Feature groups (project_features)

- **Numeric:** recommended/final amounts, total_expenditure, cost_variation_pct, expenditure_ratio, payment count/avg/max/min/frequency, pending & successful payment counts, vendor stats, recommendation→completion days, days_since_recommendation, average_rating, peer median/mean/std cost, cost_deviation_from_peer, description_similarity_score.
- **Categorical:** mp_name, state, constituency, category, house, primary_vendor (master only).
- **Text:** work_description, clean_description.

## Rules for the ML teammate

1. Train/score on `project_features.csv`; join everything on `project_id`.
2. Review missingness first — do **not** impute values that don't exist in the source.
3. `description_similarity_score` is a **text-reuse indicator**, not a fraud conclusion.
4. Return anomaly outputs as risk indicators with human-readable reasons — never confirmed-fraud labels.

## Unavailable & forbidden features

| Feature | Status |
|---|---|
| `physical_progress_pct` | ❌ **Banned** — legacy artificial placeholder, excluded from the dataset |
| Image embeddings | ❌ No image files exist |
| latitude / longitude | ❌ Not present in source (see `data/location/` — 96 synthetic demo rows only) |

## Known limitations

- Completed-works source has 43,895 missing values; MP summary has 770 — retained as quality information, not filled.
- Expenditure matching is conservative: 75,335 unmatched / 426 ambiguous — never force a match.
- Similarity data has 66 fewer rows than projects (descriptions unusable for those).
- Payment-derived signals carry the matching uncertainty above.
