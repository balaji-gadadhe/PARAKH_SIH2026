# Location Layer — ML Handoff

**Point doc.** Full method, features, and rules: `README_LOCATION.md` (same folder).

## Use for ML

- Join `project_location_features.csv` / `project_similarity_location.csv` on **`project_id`**.
- `demo/` files are **demo-only** — never production training or official decisions.

## Non-negotiables

1. Missing location ⇒ `NULL` (distance, proximity, combined score) with `similarity_method = description_only` — never zero, never "suspicious".
2. Synthetic rows (`location_is_synthetic = true`) stay isolated from production training.
3. Proximity is a supporting signal, not a risk verdict.
