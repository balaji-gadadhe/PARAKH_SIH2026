"""Project-level aggregation of similarity pair evidence."""
from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


DEFAULT_SCORE_WEIGHTS = {
    "similarity": 50.0,
    "duplicate_count": 15.0,
    "cross_mp": 15.0,
    "location": 10.0,
    "budget_inflation": 10.0,
}

OUTPUT_COLUMNS = [
    "project_id",
    "max_similarity_score",
    "duplicate_count",
    "exact_text_duplicate_flag",
    "high_text_similarity_flag",
    "generic_template_pair_flag",
    "cross_mp_duplicate_flag",
    "same_constituency_duplicate_flag",
    "same_state_duplicate_flag",
    "different_state_duplicate_flag",
    "max_cost_ratio",
    "budget_inflation_flag",
    "location_data_available",
    "location_source",
    "duplicate_risk_score",
]


def _normalise_pairs(pairs_df: pd.DataFrame) -> pd.DataFrame:
    """Make pair direction irrelevant and remove repeated relationships."""
    if pairs_df.empty:
        return pairs_df.copy()

    pairs = pairs_df.copy()
    pairs["_pair_key"] = pairs.apply(
        lambda row: tuple(sorted((str(row["project_id_a"]), str(row["project_id_b"]))),),
        axis=1,
    )
    pairs = pairs[pairs["_pair_key"].map(lambda key: key[0] != key[1])]
    pairs = pairs.drop_duplicates("_pair_key", keep="first")
    return pairs.drop(columns="_pair_key")


def _as_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if pd.notna(number) and number >= 0 else default


def build_project_similarity_features(
    pairs_df: pd.DataFrame,
    project_ids: Optional[Iterable[object]] = None,
    score_weights: Optional[dict[str, float]] = None,
    location_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Aggregate annotated pair evidence into one deterministic row per project.

    ``project_ids`` should contain the source project's IDs so projects without
    duplicate pairs are retained with zero-valued features.
    """
    required = {"project_id_a", "project_id_b", "similarity_score"}
    missing = required.difference(pairs_df.columns)
    if missing:
        raise ValueError(f"Missing required pair columns: {sorted(missing)}")

    pairs = _normalise_pairs(pairs_df)
    ids = {str(project_id) for project_id in (project_ids if project_ids is not None else [])}
    if not pairs.empty:
        ids.update(pairs["project_id_a"].astype(str))
        ids.update(pairs["project_id_b"].astype(str))

    rows = {
        project_id: {
            "project_id": project_id,
            "max_similarity_score": 0.0,
            "duplicate_count": 0,
            "exact_text_duplicate_flag": 0,
            "high_text_similarity_flag": 0,
            "generic_template_pair_flag": 0,
            "cross_mp_duplicate_flag": 0,
            "same_constituency_duplicate_flag": 0,
            "same_state_duplicate_flag": 0,
            "different_state_duplicate_flag": 0,
            "max_cost_ratio": 0.0,
            "budget_inflation_flag": 0,
            "location_data_available": 0,
            "location_source": "administrative_area",
        }
        for project_id in ids
    }

    weights = DEFAULT_SCORE_WEIGHTS.copy()
    if score_weights:
        weights.update(score_weights)

    location_weights = {
        "SAME_CONSTITUENCY": 1.0,
        "SAME_STATE_DIFF_CONST": 0.7,
        "DIFF_STATE": 0.4,
    }
    location_scores = {project_id: 0.0 for project_id in rows}
    if location_df is not None and not location_df.empty:
        location_ids = set(location_df["project_id"].astype(str))
        for project_id in location_ids.intersection(rows):
            rows[project_id]["location_data_available"] = 1
            rows[project_id]["location_source"] = "verified_gps_metadata_only"

    for _, pair in pairs.iterrows():
        project_a = str(pair["project_id_a"])
        project_b = str(pair["project_id_b"])
        relationship = str(pair.get("geo_relationship", ""))
        similarity = _as_number(pair.get("similarity_score"))
        cost_ratio = _as_number(pair.get("cost_ratio"))
        is_exact_text = similarity >= 0.97
        is_high_text = similarity >= 0.85
        is_generic_pair = str(pair.get("is_generic_a", "")).lower() == "true" or str(pair.get("is_generic_b", "")).lower() == "true"
        is_cross_mp = str(pair.get("mp_a", "")) != str(pair.get("mp_b", ""))
        budget_flag = str(pair.get("budget_anomaly_label", "")).upper() in {
            "HIGH_BUDGET_INFLATION", "CRITICAL_BUDGET_INFLATION"
        }

        for project_id in (project_a, project_b):
            row = rows[project_id]
            row["duplicate_count"] += 1
            row["max_similarity_score"] = max(row["max_similarity_score"], similarity)
            row["exact_text_duplicate_flag"] = max(row["exact_text_duplicate_flag"], int(is_exact_text))
            row["high_text_similarity_flag"] = max(row["high_text_similarity_flag"], int(is_high_text))
            row["generic_template_pair_flag"] = max(row["generic_template_pair_flag"], int(is_generic_pair))
            row["max_cost_ratio"] = max(row["max_cost_ratio"], cost_ratio)
            row["cross_mp_duplicate_flag"] = max(row["cross_mp_duplicate_flag"], int(is_cross_mp))
            row["same_constituency_duplicate_flag"] = max(
                row["same_constituency_duplicate_flag"], int(relationship == "SAME_CONSTITUENCY")
            )
            row["same_state_duplicate_flag"] = max(
                row["same_state_duplicate_flag"], int(relationship == "SAME_STATE_DIFF_CONST")
            )
            row["different_state_duplicate_flag"] = max(
                row["different_state_duplicate_flag"], int(relationship == "DIFF_STATE")
            )
            row["budget_inflation_flag"] = max(row["budget_inflation_flag"], int(budget_flag))
            location_scores[project_id] = max(
                location_scores[project_id], location_weights.get(relationship, 0.0)
            )

    output = pd.DataFrame(rows.values(), columns=OUTPUT_COLUMNS[:-1])
    output["duplicate_risk_score"] = (
        output["max_similarity_score"] * weights["similarity"]
        + (output["duplicate_count"].clip(upper=10) / 10.0) * weights["duplicate_count"]
        + output["cross_mp_duplicate_flag"] * weights["cross_mp"]
        + output["project_id"].map(location_scores).fillna(0.0) * weights["location"]
        + output["budget_inflation_flag"] * weights["budget_inflation"]
    ).clip(upper=100.0).round(4)

    numeric_columns = [
        column for column in OUTPUT_COLUMNS
        if column not in {"project_id", "location_source"}
    ]
    output[numeric_columns] = output[numeric_columns].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    flag_columns = [column for column in OUTPUT_COLUMNS if column.endswith("flag")]
    output[flag_columns] = output[flag_columns].astype("int64")
    output["location_data_available"] = output["location_data_available"].astype("int64")
    output["duplicate_count"] = output["duplicate_count"].astype("int64")
    return output.sort_values("project_id").reset_index(drop=True)[OUTPUT_COLUMNS]
