"""
test_similarity_engine.py
===========================
MPLAD-Sentinel | Similarity Engine Test Suite

Tests:
  1. Verbatim duplicate pair detection (identical descriptions across MPs)
  2. Generic template filter — ensures "cc road" is NOT flagged as suspicious
  3. Budget discrepancy calculation on identical pairs (>2x inflation)
  4. Location proximity classification (same-constituency, cross-state, etc.)
  5. Zero-division and None-safety for all modules
  6. Image hashing stub/mock mode

Run:
    python test_similarity_engine.py
"""
from __future__ import annotations
import sys
import os
import warnings
warnings.filterwarnings("ignore")
FEATURES_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, FEATURES_ROOT)

import pandas as pd
import numpy as np

from analytics.similarity_engine.text_similarity_tfidf import TextSimilarityEngine
from analytics.similarity_engine.location_proximity import LocationProximity
from analytics.similarity_engine.cost_similarity import CostSimilarityAnalyser
from analytics.similarity_engine.image_hashing import ImageHasher
from analytics.similarity_engine.project_similarity_features import build_project_similarity_features

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 65
failures = []

def check(test_name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  {PASS}  {test_name}")
    else:
        print(f"  {FAIL}  {test_name}  {detail}")
        failures.append(test_name)


# ─────────────────────────────────────────────────────────────────────────────
# Shared synthetic dataset
# ─────────────────────────────────────────────────────────────────────────────
SYNTHETIC_DESCRIPTIONS = pd.DataFrame([
    # Verbatim copies — should be flagged
    {
        "project_id": "P001|MP_ALPHA|GUJARAT|SURAT",
        "clean_description": "construction of cc motorable road between govt primary school and sri ganesh mandir at surat ward no 18 near old bus stand",
        "state": "Gujarat", "constituency": "SURAT",
        "work_description": "same", "category": "ROAD", "description_similarity_score": 1.0,
    },
    {
        "project_id": "P002|MP_BETA|GUJARAT|VADODARA",
        "clean_description": "construction of cc motorable road between govt primary school and sri ganesh mandir at surat ward no 18 near old bus stand",
        "state": "Gujarat", "constituency": "VADODARA",
        "work_description": "same", "category": "ROAD", "description_similarity_score": 1.0,
    },
    # Generic templates — should NOT be flagged as suspicious
    {
        "project_id": "P003|MP_GAMMA|RAJASTHAN|JAIPUR",
        "clean_description": "cc road",
        "state": "Rajasthan", "constituency": "JAIPUR",
        "work_description": "cc road", "category": "ROAD", "description_similarity_score": 1.0,
    },
    {
        "project_id": "P004|MP_DELTA|RAJASTHAN|JODHPUR",
        "clean_description": "solar light",
        "state": "Rajasthan", "constituency": "JODHPUR",
        "work_description": "solar light", "category": "ELECTRIFICATION", "description_similarity_score": 1.0,
    },
    # Unique specific description — should have low score
    {
        "project_id": "P005|MP_EPS|KERALA|TRIVANDRUM",
        "clean_description": "construction of elevated pedestrian bridge over central canal connecting east and west zones of trivandrum city near medical college junction",
        "state": "Kerala", "constituency": "TRIVANDRUM",
        "work_description": "unique", "category": "BRIDGE", "description_similarity_score": 0.2,
    },
    # Same-constituency verbatim pair — critical double billing risk
    {
        "project_id": "P006|MP_ZETA|MAHARASHTRA|PUNE",
        "clean_description": "renovation and upgradation of community health centre at hadapsar ward 15 with provision of new ot block and diagnostic lab pune",
        "state": "Maharashtra", "constituency": "PUNE",
        "work_description": "same", "category": "HEALTH", "description_similarity_score": 0.99,
    },
    {
        "project_id": "P007|MP_ZETA|MAHARASHTRA|PUNE",
        "clean_description": "renovation and upgradation of community health centre at hadapsar ward 15 with provision of new ot block and diagnostic lab pune",
        "state": "Maharashtra", "constituency": "PUNE",
        "work_description": "same", "category": "HEALTH", "description_similarity_score": 0.99,
    },
])

SYNTHETIC_FEATURES = pd.DataFrame([
    {"project_id": "P001|MP_ALPHA|GUJARAT|SURAT",        "recommended_amount": 500000,  "state": "Gujarat",     "constituency": "SURAT",     "total_expenditure": 480000, "category": "ROAD"},
    {"project_id": "P002|MP_BETA|GUJARAT|VADODARA",       "recommended_amount": 1500000, "state": "Gujarat",     "constituency": "VADODARA",  "total_expenditure": 1400000,"category": "ROAD"},
    {"project_id": "P003|MP_GAMMA|RAJASTHAN|JAIPUR",      "recommended_amount": 50000,   "state": "Rajasthan",   "constituency": "JAIPUR",    "total_expenditure": 45000,  "category": "ROAD"},
    {"project_id": "P004|MP_DELTA|RAJASTHAN|JODHPUR",     "recommended_amount": 60000,   "state": "Rajasthan",   "constituency": "JODHPUR",   "total_expenditure": 55000,  "category": "ELECTRIFICATION"},
    {"project_id": "P005|MP_EPS|KERALA|TRIVANDRUM",       "recommended_amount": 12000000,"state": "Kerala",      "constituency": "TRIVANDRUM","total_expenditure": 9000000,"category": "BRIDGE"},
    {"project_id": "P006|MP_ZETA|MAHARASHTRA|PUNE",       "recommended_amount": 800000,  "state": "Maharashtra", "constituency": "PUNE",      "total_expenditure": 780000, "category": "HEALTH"},
    {"project_id": "P007|MP_ZETA|MAHARASHTRA|PUNE",       "recommended_amount": 800000,  "state": "Maharashtra", "constituency": "PUNE",      "total_expenditure": 780000, "category": "HEALTH"},
])


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: TF-IDF Engine — verbatim duplicate detection
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 1: Verbatim Duplicate Pair Detection")
print(SEP)
engine = TextSimilarityEngine(high_threshold=0.80)
engine.fit(SYNTHETIC_DESCRIPTIONS)

pairs = engine.find_duplicate_pairs(SYNTHETIC_DESCRIPTIONS, similarity_threshold=0.80)

# P001 and P002 are verbatim — should be detected as a pair
p1_p2_found = not pairs.empty and any(
    (pairs["project_id_a"].str.startswith("P001") & pairs["project_id_b"].str.startswith("P002")) |
    (pairs["project_id_a"].str.startswith("P002") & pairs["project_id_b"].str.startswith("P001"))
)
check("Verbatim cross-constituency pair (P001, P002) detected", p1_p2_found)

# P006 and P007 are same-constituency verbatim — should be detected
p6_p7_found = not pairs.empty and any(
    (pairs["project_id_a"].str.startswith("P006") & pairs["project_id_b"].str.startswith("P007")) |
    (pairs["project_id_a"].str.startswith("P007") & pairs["project_id_b"].str.startswith("P006"))
)
check("Same-constituency verbatim pair (P006, P007) detected", p6_p7_found)

p1_p2 = pairs[
    pairs["project_id_a"].str.startswith("P001") &
    pairs["project_id_b"].str.startswith("P002")
]
check(
    "MP names are recovered from composite project IDs",
    not p1_p2.empty and p1_p2.iloc[0]["mp_a"] == "MP_ALPHA" and p1_p2.iloc[0]["mp_b"] == "MP_BETA",
)

# Unique project P005 should NOT be paired
p5_found = not pairs.empty and any(
    pairs["project_id_a"].str.startswith("P005") | pairs["project_id_b"].str.startswith("P005")
)
check("Unique project P005 is NOT in any pair", not p5_found)

# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Generic Template Filter
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 2: Generic Template Filter")
print(SEP)
check("'cc road' is generic template",         TextSimilarityEngine.is_generic_template("cc road"))
check("'solar light' is generic template",     TextSimilarityEngine.is_generic_template("solar light"))
check("'muktidham nirman' is generic (short)", TextSimilarityEngine.is_generic_template("muktidham nirman"))
check(
    "Long specific description is NOT generic",
    not TextSimilarityEngine.is_generic_template(
        "construction of elevated pedestrian bridge over central canal connecting east and west zones"
    ),
)
check("None input is treated as generic", TextSimilarityEngine.is_generic_template(None))
check("Empty string is treated as generic", TextSimilarityEngine.is_generic_template(""))

# Per-project scores: generic projects should score near 0.05
scores = engine.score_all(SYNTHETIC_DESCRIPTIONS)
check("Generic project P003 scores <= 0.05", scores.get("P003|MP_GAMMA|RAJASTHAN|JAIPUR", 1.0) <= 0.05)
check("Generic project P004 scores <= 0.05", scores.get("P004|MP_DELTA|RAJASTHAN|JODHPUR", 1.0) <= 0.05)
check("Unique specific project P005 scores <= 0.10", scores.get("P005|MP_EPS|KERALA|TRIVANDRUM", 1.0) <= 0.10)

# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Budget Discrepancy on Identical Pairs
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 3: Budget Discrepancy (Cost Similarity)")
print(SEP)
csa = CostSimilarityAnalyser()

# P001 (500k) vs P002 (1500k) => ratio = 3.0 => BUDGET_INFLATION
if not pairs.empty:
    annotated = csa.annotate_pairs(pairs, SYNTHETIC_FEATURES)
    p1_p2_pair = annotated[
        (annotated["project_id_a"].str.startswith("P001") | annotated["project_id_b"].str.startswith("P001"))
    ]
    if not p1_p2_pair.empty:
        ratio = p1_p2_pair.iloc[0]["cost_ratio"]
        label = p1_p2_pair.iloc[0]["budget_anomaly_label"]
        check(f"P001 vs P002 cost_ratio=3.0", abs(ratio - 3.0) < 0.01, f"got {ratio}")
        check("P001 vs P002 labelled HIGH_BUDGET_INFLATION", "INFLATION" in label, f"got {label}")
    else:
        check("P001-P002 pair present in annotated output", False, "pair missing")
else:
    check("Pairs exist for cost annotation", False, "no pairs found")

# Safe ratio — zero cost
check("safe_ratio(0, 500) = 0.0", csa._safe_ratio(0, 500) == 0.0)
check("safe_ratio(-100, 200) = 0.0", csa._safe_ratio(-100, 200) == 0.0)
check("safe_ratio(200, 100) = 2.0", csa._safe_ratio(200, 100) == 2.0)
check("safe_ratio(None, 100) = 0.0", csa._safe_ratio(None, 100) == 0.0)

# Peer deviation
peer_df = csa.compute_peer_deviation(SYNTHETIC_FEATURES)
check("peer_deviation returns correct shape", len(peer_df) == len(SYNTHETIC_FEATURES))
check("peer_deviation_score is between 0 and 1", all((peer_df["peer_deviation_score"] >= 0) & (peer_df["peer_deviation_score"] <= 1)))
check("cost_deviation_label column is present", "cost_deviation_label" in peer_df.columns)

# ─────────────────────────────────────────────────────────────────────────────
# Test 3b: Project-level similarity feature aggregation
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 3b: Project-Level Similarity Feature Aggregation")
print(SEP)
aggregation_pairs = pd.DataFrame([
    {"project_id_a": "A", "project_id_b": "B", "similarity_score": 0.991,
     "mp_a": "MP1", "mp_b": "MP2", "geo_relationship": "SAME_STATE_DIFF_CONST",
     "cost_ratio": 2.3, "budget_anomaly_label": "HIGH_BUDGET_INFLATION"},
    {"project_id_a": "B", "project_id_b": "A", "similarity_score": 0.991,
     "mp_a": "MP2", "mp_b": "MP1", "geo_relationship": "SAME_STATE_DIFF_CONST",
     "cost_ratio": 2.3, "budget_anomaly_label": "HIGH_BUDGET_INFLATION"},
    {"project_id_a": "A", "project_id_b": "C", "similarity_score": 0.984,
     "mp_a": "MP1", "mp_b": "MP1", "geo_relationship": "SAME_CONSTITUENCY",
     "cost_ratio": 1.1, "budget_anomaly_label": "NORMAL_COST"},
    {"project_id_a": "B", "project_id_b": "D", "similarity_score": 0.976,
     "mp_a": "MP2", "mp_b": "MP3", "geo_relationship": "DIFF_STATE",
     "cost_ratio": float("nan"), "budget_anomaly_label": "MISSING_COST"},
])
aggregated = build_project_similarity_features(
    aggregation_pairs, project_ids=["A", "B", "C", "D", "E"]
)
row_a = aggregated[aggregated["project_id"] == "A"].iloc[0]
row_b = aggregated[aggregated["project_id"] == "B"].iloc[0]
row_c = aggregated[aggregated["project_id"] == "C"].iloc[0]
row_d = aggregated[aggregated["project_id"] == "D"].iloc[0]
row_e = aggregated[aggregated["project_id"] == "E"].iloc[0]
check("Project with no duplicate is retained", row_e["duplicate_count"] == 0)
check("One-row-per-project output", len(aggregated) == 5)
check("project_id values are unique", aggregated["project_id"].is_unique)
check("Multiple duplicates aggregate maximum similarity", row_a["max_similarity_score"] == 0.991)
check("Duplicate A-B/B-A counted once", row_b["duplicate_count"] == 2)
check("Cross-MP flag is set", row_a["cross_mp_duplicate_flag"] == 1)
check("Exact-text flag is set", row_a["exact_text_duplicate_flag"] == 1)
check("High-text-similarity flag is set", row_a["high_text_similarity_flag"] == 1)
check("Generic-template pair flag is set", row_a["generic_template_pair_flag"] == 0)
check("Same-constituency flag is set", row_a["same_constituency_duplicate_flag"] == 1)
check("Same-state/different-constituency flag is set", row_a["same_state_duplicate_flag"] == 1)
check("Different-state flag is set", row_b["different_state_duplicate_flag"] == 1)
check("Maximum cost ratio aggregates", row_a["max_cost_ratio"] == 2.3)
check("Missing cost values safely become zero", row_d["max_cost_ratio"] == 0.0)
check("Budget inflation flag uses existing labels", row_a["budget_inflation_flag"] == 1)
check("No budget flag for normal/missing costs", row_c["budget_inflation_flag"] == 0)
check("Risk score is bounded 0-100", bool(aggregated["duplicate_risk_score"].between(0, 100).all()))
location_test_df = pd.DataFrame([
    {"project_id": "REAL", "latitude": 20.0, "longitude": 73.0,
     "location_source": "real", "is_verified": True},
    {"project_id": "SYNTHETIC", "latitude": 20.001, "longitude": 73.001,
     "location_source": "synthetic_demo", "is_verified": False,
     "location_is_synthetic": True},
    {"project_id": "INVALID", "latitude": 200.0, "longitude": 73.0,
     "location_source": "real", "is_verified": True},
])
verified_locations = LocationProximity.verified_coordinate_rows(location_test_df)
location_aggregated = build_project_similarity_features(
    aggregation_pairs,
    project_ids=["A", "B", "C", "D", "E", "REAL", "SYNTHETIC"],
    location_df=verified_locations,
)
check("Project-level verified GPS flag is available", location_aggregated.loc[location_aggregated["project_id"] == "REAL", "location_data_available"].iloc[0] == 1)
check("Project-level unverified GPS remains unavailable", location_aggregated.loc[location_aggregated["project_id"] == "SYNTHETIC", "location_data_available"].iloc[0] == 0)
empty_aggregated = build_project_similarity_features(
    pd.DataFrame(columns=["project_id_a", "project_id_b", "similarity_score"]),
    project_ids=["EMPTY_PROJECT"],
)
check("Empty similarity result retains source project", len(empty_aggregated) == 1)
check("Empty similarity result has zero features", empty_aggregated.iloc[0]["duplicate_count"] == 0)

# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Location Proximity Classification
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 4: Location Proximity Classification")
print(SEP)
lp = LocationProximity()

check("Same state+constituency => SAME_CONSTITUENCY",
    lp.classify_pair("Gujarat","SURAT","Gujarat","SURAT") == "SAME_CONSTITUENCY")
check("Same state, diff constituency => SAME_STATE_DIFF_CONST",
    lp.classify_pair("Gujarat","SURAT","Gujarat","VADODARA") == "SAME_STATE_DIFF_CONST")
check("Different states => DIFF_STATE",
    lp.classify_pair("Gujarat","SURAT","Kerala","TRIVANDRUM") == "DIFF_STATE")
check(
    "GPS distance for nearby points is approximately 111 m",
    abs(lp.haversine_distance_m(20.0000, 73.0000, 20.0010, 73.0000) - 111.19) < 1.0,
)
check("GPS distance <=100 m => SAME_SITE", lp.distance_band(100.0) == "SAME_SITE")
check("GPS distance <=1 km => NEARBY", lp.distance_band(1000.0) == "NEARBY")
check("GPS distance >1 km => SEPARATE", lp.distance_band(1000.1) == "SEPARATE")
check("Invalid GPS coordinates => unavailable", lp.distance_band(None) == "GPS_UNAVAILABLE")
check("Only valid real/verified GPS rows are accepted", verified_locations["project_id"].tolist() == ["REAL"])
check("Synthetic GPS rows are excluded", "SYNTHETIC" not in set(verified_locations["project_id"]))
check("Invalid GPS rows are excluded", "INVALID" not in set(verified_locations["project_id"]))
check("Null constituency => UNKNOWN",
    lp.classify_pair("Gujarat", None, "Gujarat","SURAT") == "UNKNOWN")
check("Empty constituency => UNKNOWN",
    lp.classify_pair("Gujarat","","Gujarat","SURAT") == "UNKNOWN")

# Risk weights
check("SAME_CONSTITUENCY weight = 1.0",    lp.get_risk_weight("SAME_CONSTITUENCY") == 1.0)
check("SAME_STATE_DIFF_CONST weight = 0.7", lp.get_risk_weight("SAME_STATE_DIFF_CONST") == 0.7)
check("DIFF_STATE weight = 0.4",            lp.get_risk_weight("DIFF_STATE") == 0.4)

# Annotate pairs
if not pairs.empty:
    annotated_geo = lp.annotate_pairs(pairs.copy())
    check("geo_relationship column added to pairs", "geo_relationship" in annotated_geo.columns)
    check("geo_risk_weight column added to pairs",  "geo_risk_weight"  in annotated_geo.columns)
    check("GPS is not used for pair annotation", (annotated_geo["location_proximity"] == "GPS_NOT_USED").all())
    # P006-P007 are same-constituency — verify
    p6_p7 = annotated_geo[
        annotated_geo["project_id_a"].str.startswith("P006") |
        annotated_geo["project_id_b"].str.startswith("P006")
    ]
    if not p6_p7.empty:
        check("P006-P007 geo_relationship = SAME_CONSTITUENCY",
            p6_p7.iloc[0]["geo_relationship"] == "SAME_CONSTITUENCY")

# ─────────────────────────────────────────────────────────────────────────────
# Test 5: None / Edge Case Safety
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 5: None / Edge-Case Safety")
print(SEP)
check("LocationProximity handles all-None inputs",
    lp.classify_pair(None, None, None, None) == "UNKNOWN")
check("specificity_weight(None) = 0.0",
    TextSimilarityEngine._specificity_weight(None) == 0.0)
check("specificity_weight('') = 0.0",
    TextSimilarityEngine._specificity_weight("") == 0.0)
check("_clean(None) returns empty string",
    TextSimilarityEngine._clean(None) == "")
check("annotate_pairs on empty DataFrame returns empty",
    lp.annotate_pairs(pd.DataFrame()).empty)

empty_feat = pd.DataFrame(columns=["project_id","recommended_amount","state","category"])
peer_empty = csa.compute_peer_deviation(empty_feat)
check("compute_peer_deviation on empty df returns empty", len(peer_empty) == 0)

# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Image Hashing (Stub / Mock mode)
# ─────────────────────────────────────────────────────────────────────────────
print(SEP)
print("TEST 6: Image Hashing (Mock/Stub Mode)")
print(SEP)
hasher = ImageHasher()
mock_result = hasher.create_mock_hash_result(hamming_distance=3, is_duplicate=True)
check("Mock ImageHashResult is_duplicate=True",  mock_result.is_duplicate == True)
check("Mock ImageHashResult hamming_phash=3",    mock_result.hamming_phash == 3)
check("Mock ImageHashResult confidence > 0.9",   mock_result.confidence > 0.90)

mock_non_dup = hasher.create_mock_hash_result(hamming_distance=30, is_duplicate=False)
check("Mock non-duplicate is_duplicate=False",   mock_non_dup.is_duplicate == False)

# Missing image fallback
result_missing = hasher.compare_images("nonexistent_a.jpg", "nonexistent_b.jpg")
check("Missing image files => is_duplicate=False (no crash)", result_missing.is_duplicate == False)
check("Missing image result.reason is non-empty",            len(result_missing.reason) > 0)

# Cross-project with empty map
cross = hasher.find_cross_project_image_duplicates({})
check("Empty project_image_map returns empty list", cross == [])

# ─────────────────────────────────────────────────────────────────────────────
# FINAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 65)
if failures:
    print(f"  RESULT: {len(failures)} TEST(S) FAILED")
    for f in failures:
        print(f"    - {f}")
else:
    print("  RESULT: ALL TESTS PASSED (0 failures)")
print("=" * 65)


def test_similarity_engine_suite():
    """Pytest entry point for similarity engine test checks."""
    assert len(failures) == 0, f"{len(failures)} similarity tests failed: {failures}"


if __name__ == "__main__":
    sys.exit(1 if failures else 0)
