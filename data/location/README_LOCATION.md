# PARAKH Location-Proximity Layer

⚠️ **Demo artifact — 0 real coordinates. 96 synthetic demo rows only, always labeled.** Geo features are deferred (D-009); never present synthetic coordinates as official project locations.

## What's here

| File | Contents |
|---|---|
| `project_locations.csv` | All official project IDs; coordinate fields **explicitly unavailable** (`location_source = not_available`) — never manufactured |
| `project_location_features.csv` | Per-project proximity features (join on `project_id`) |
| `project_similarity_location.csv` | Similarity augmented with proximity |
| `demo/demo_project_locations.csv` · `demo/demo_project_similarity_location.csv` | Synthetic demo set (`location_source = synthetic_demo`, `is_verified = false`, `demo_only = true`) — **never merge into official data** |

Rebuild with `scripts/location/build_location_dataset.py` → `build_proximity_features.py` → `validate_location_data.py` (writes `location_validation_report.csv`).

## Join key

`project_id` — join `project_location_features.csv` onto `project_features.csv`.

## Feature meanings

`latitude/longitude` (only when data exists) · `nearest_project_id` / `nearest_project_distance_km` · `nearby_projects_500m/1km/5km` · `same_constituency_project_count` · `local_project_density` (5 km radius) · `nearest_same_constituency_distance_km` · `location_data_available` · `location_is_synthetic`.

## Method

- **Haversine** great-circle distance, R = 6371 km (never naive lat/lon subtraction).
- **Proximity score:** `exp(-distance_km / 5)` — [0,1], closer = higher.
- **Combined similarity** (only when both exist): `0.6 × description_similarity + 0.4 × location_proximity`.
- **Missing location ⇒ NULL, not zero** — zero would fake a valid zero-distance relationship.

## ML usage rules

1. Use NULL handling for missing geo features — missing is unknown, not suspicious and not zero.
2. Keep synthetic demo rows out of any production training set.
3. Geographic proximity is a **contextual signal**, not proof of fraud or duplication.
4. Production geo enrichment requires verified geocoding from approved sources — future work.

## Known limitations

- Current MPLADS source data provides no reliable project coordinates.
- Synthetic rows exist only to demonstrate proximity behavior.
- Similarity outputs remove self-pairs (`project_id == similar_project_id`).
- Validation report tracks: real/synthetic/not_available counts, invalid coordinates, duplicate IDs/coords, self-pairs, proximity counts, description-only vs description+location splits.
