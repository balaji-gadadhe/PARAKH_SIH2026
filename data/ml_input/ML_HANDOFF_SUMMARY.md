# PARAKH ML Handoff Summary

**Status: ready for ML use.** Full dataset/feature/limitation details: `README_ML.md` (same folder).

## TL;DR for the ML teammate

1. **Primary dataset:** `project_features.csv` (86,976 × 30) · **key:** `project_id`.
2. Also available: `mp_features.csv` (774), `project_similarity_data.csv` (86,910), `vendor_features.csv` (28,123), `data_dictionary.xlsx`.
3. **Do not use:** `physical_progress_pct` (banned legacy placeholder), fabricated GPS, image embeddings — none exist.
4. Missing values are real missingness — don't impute what the source never had.
5. Outputs = **risk indicators with reasons** (potential anomaly / requires investigation), never confirmed-fraud labels.

## Related engineering outputs

- `data/master/master_works.csv` (86,976) · `data/master/master_mp_summary.csv` (774)
- Validation reports under `data/validation/` (quality, missing values, expenditure matching: 302 matched / 426 ambiguous / 75,335 unmatched)
