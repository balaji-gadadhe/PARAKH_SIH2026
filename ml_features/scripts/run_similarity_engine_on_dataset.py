"""
run_similarity_engine_on_dataset.py
=====================================
MPLAD-Sentinel | Similarity & Duplicate Detection Engine — Full Dataset Runner

Runs the complete similarity pipeline across all 86,910 real MPLADS project
descriptions and generates:
  similarity_outputs/duplicate_project_pairs.csv
  similarity_outputs/similarity_summary.csv
  Updates rule_outputs/verification_input.csv with similarity_anomaly_score

Usage:
    python run_similarity_engine_on_dataset.py
    python run_similarity_engine_on_dataset.py --pair_threshold 0.90
    python run_similarity_engine_on_dataset.py --project_id "161333|..."
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import time
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("SimilarityPipeline")

# ── Path constants ─────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT      = os.path.dirname(BASE_DIR)
SIM_DATA_PATH  = os.path.join(BASE_DIR, "ml_input", "project_similarity_data.csv")
FEAT_DATA_PATH = os.path.join(BASE_DIR, "ml_input", "project_features.csv")
VERIF_PATH     = os.path.join(BASE_DIR, "ml_outputs", "rules", "verification_input.csv")
OUTPUT_DIR     = os.path.join(BASE_DIR, "ml_outputs", "similarity")
PAIRS_PATH     = os.path.join(OUTPUT_DIR, "duplicate_project_pairs.csv")
SUMMARY_PATH   = os.path.join(OUTPUT_DIR, "similarity_summary.csv")
PROJECT_FEATURES_PATH = os.path.join(OUTPUT_DIR, "project_similarity_features.csv")
LOCATION_PATH  = os.path.join(BASE_DIR, "ml_input", "project_location_lookup.csv")
LOCATION_LAYER_PATH = os.path.join(REPO_ROOT, "data", "location", "project_locations.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)
sys.path.insert(0, BASE_DIR)

# ── Similarity Engine imports ──────────────────────────────────────────────────
from analytics.similarity_engine.text_similarity_tfidf import TextSimilarityEngine
from analytics.similarity_engine.location_proximity import LocationProximity
from analytics.similarity_engine.cost_similarity import CostSimilarityAnalyser
from analytics.similarity_engine.project_similarity_features import build_project_similarity_features

SEPARATOR = "=" * 78


# ── Composite risk band helper ────────────────────────────────────────────────
def similarity_risk_band(score: float) -> str:
    if score >= 0.80:  return "CRITICAL_DUPLICATE"
    if score >= 0.60:  return "HIGH_SIMILARITY"
    if score >= 0.40:  return "MEDIUM_SIMILARITY"
    if score >= 0.10:  return "LOW_SIMILARITY"
    return "UNIQUE"


# ── Main pipeline ─────────────────────────────────────────────────────────────
def run_pipeline(pair_threshold: float = 0.85) -> None:
    print(SEPARATOR)
    print("   MPLAD-Sentinel | Similarity & Duplicate Detection Engine")
    print(SEPARATOR)
    t0 = time.perf_counter()

    # ── 1. Load datasets ───────────────────────────────────────────────────────
    logger.info("Loading datasets...")
    df_sim  = pd.read_csv(SIM_DATA_PATH, low_memory=False)
    df_feat = pd.read_csv(FEAT_DATA_PATH, low_memory=False)
    logger.info("  Similarity data : %d rows x %d cols", *df_sim.shape)
    logger.info("  Feature data    : %d rows x %d cols", *df_feat.shape)

    location_df = None
    location_path = LOCATION_LAYER_PATH if os.path.isfile(LOCATION_LAYER_PATH) else LOCATION_PATH
    if os.path.isfile(location_path):
        raw_location_df = pd.read_csv(location_path, low_memory=False)
        location_df = LocationProximity.verified_coordinate_rows(raw_location_df)
        logger.info(
            "  Location layer  : %d rows read, %d verified real GPS rows used (%s)",
            len(raw_location_df), len(location_df), location_path,
        )
    else:
        logger.info("  Location layer  : not found; using administrative area only")

    # ── 2. Train TF-IDF ───────────────────────────────────────────────────────
    logger.info("Training TF-IDF vectorizer on %d descriptions...", len(df_sim))
    engine = TextSimilarityEngine(high_threshold=pair_threshold)
    engine.fit(df_sim)

    # ── 3. Find duplicate pairs ───────────────────────────────────────────────
    logger.info("Finding duplicate pairs (threshold=%.2f)...", pair_threshold)
    pairs_df = engine.find_duplicate_pairs(df_sim, similarity_threshold=pair_threshold)

    # ── 4. Annotate: location + cost ─────────────────────────────────────────
    logger.info("Annotating pairs with geographic risk...")
    lp = LocationProximity()
    pairs_df = lp.annotate_pairs(pairs_df, location_df=location_df)

    logger.info("Annotating pairs with cost discrepancy...")
    csa = CostSimilarityAnalyser()
    pairs_df = csa.annotate_pairs(pairs_df, df_feat)

    # ── 5. Add composite pair-level risk score ─────────────────────────────────
    pairs_df["pair_risk_score"] = pairs_df.apply(
        lambda r: csa.pair_cost_risk_score(
            text_similarity=r["similarity_score"],
            cost_ratio=r.get("cost_ratio", 1.0),
            geo_weight=r.get("geo_risk_weight", 0.5),
        ),
        axis=1,
    )

    # ── 6. Save pairs ─────────────────────────────────────────────────────────
    if not pairs_df.empty:
        # Only export specific-description pairs for the final CSV
        specific_pairs = pairs_df[pairs_df["both_specific"] == True].copy()
        pairs_df.to_csv(PAIRS_PATH, index=False, encoding="utf-8")
        logger.info("Saved %d duplicate pairs → %s", len(pairs_df), PAIRS_PATH)
    else:
        pairs_df.to_csv(PAIRS_PATH, index=False, encoding="utf-8")
        logger.info("No pairs found. Empty file saved.")

    project_similarity_df = build_project_similarity_features(
        pairs_df,
        project_ids=df_sim["project_id"],
        location_df=location_df,
    )
    project_similarity_df.to_csv(PROJECT_FEATURES_PATH, index=False, encoding="utf-8")
    logger.info(
        "Saved %d project-level similarity rows -> %s",
        len(project_similarity_df), PROJECT_FEATURES_PATH,
    )

    # ── 7. Per-project similarity scores ──────────────────────────────────────
    logger.info("Computing per-project similarity anomaly scores...")
    scores_dict = engine.score_all(df_sim)

    df_sim["similarity_anomaly_score"] = df_sim["project_id"].map(scores_dict).fillna(0.0)
    df_sim["similarity_risk_band"]     = df_sim["similarity_anomaly_score"].apply(similarity_risk_band)

    # ── 8. Peer cost deviation per project ────────────────────────────────────
    logger.info("Computing peer cost deviation per project...")
    peer_df = csa.compute_peer_deviation(df_feat)
    df_sim = df_sim.merge(
        peer_df[["project_id", "cost_deviation_label", "peer_deviation_score"]],
        on="project_id", how="left"
    )

    # ── 9. Generate macro summary ─────────────────────────────────────────────
    total   = len(df_sim)
    summary_rows = []

    band_counts = df_sim["similarity_risk_band"].value_counts()
    for band in ["CRITICAL_DUPLICATE","HIGH_SIMILARITY","MEDIUM_SIMILARITY","LOW_SIMILARITY","UNIQUE"]:
        cnt = int(band_counts.get(band, 0))
        summary_rows.append({
            "metric": f"Projects in {band}",
            "count":  cnt,
            "pct":    round(cnt / total * 100, 2),
        })

    if not pairs_df.empty:
        summary_rows.append({
            "metric": "Total duplicate pairs found",
            "count":  len(pairs_df),
            "pct":    round(len(pairs_df) / total * 100, 2),
        })
        cross_mp = pairs_df[pairs_df["mp_a"] != pairs_df["mp_b"]]
        summary_rows.append({
            "metric": "Cross-MP duplicate pairs",
            "count":  len(cross_mp),
            "pct":    round(len(cross_mp) / max(1, len(pairs_df)) * 100, 2),
        })
        same_const = pairs_df[pairs_df["geo_relationship"] == "SAME_CONSTITUENCY"]
        summary_rows.append({
            "metric": "Same-constituency duplicate pairs",
            "count":  len(same_const),
            "pct":    round(len(same_const) / max(1, len(pairs_df)) * 100, 2),
        })
        budget_inf = pairs_df[pairs_df.get("budget_anomaly_label", pd.Series()).isin(
            ["CRITICAL_BUDGET_INFLATION","HIGH_BUDGET_INFLATION"]
        )]
        summary_rows.append({
            "metric": "Pairs with budget inflation anomaly",
            "count":  len(budget_inf),
            "pct":    round(len(budget_inf) / max(1, len(pairs_df)) * 100, 2),
        })

    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(SUMMARY_PATH, index=False, encoding="utf-8")
    logger.info("Saved similarity summary → %s", SUMMARY_PATH)

    # ── 10. Update verification_input.csv ─────────────────────────────────────
    if os.path.isfile(VERIF_PATH):
        logger.info("Updating verification_input.csv with similarity scores...")
        df_verif = pd.read_csv(VERIF_PATH, low_memory=False)
        score_update = df_sim[["project_id","similarity_anomaly_score","similarity_risk_band"]]

        # Drop old columns if they exist
        for col in ["similarity_anomaly_score","similarity_risk_band"]:
            if col in df_verif.columns:
                df_verif.drop(columns=[col], inplace=True)

        df_verif = df_verif.merge(score_update, on="project_id", how="left")
        df_verif["similarity_anomaly_score"] = df_verif["similarity_anomaly_score"].fillna(0.0)
        df_verif["similarity_risk_band"]     = df_verif["similarity_risk_band"].fillna("UNIQUE")
        df_verif.to_csv(VERIF_PATH, index=False, encoding="utf-8")
        logger.info("verification_input.csv updated with similarity scores.")
    else:
        logger.warning("verification_input.csv not found — skipping update.")

    # ── 11. Print execution summary ───────────────────────────────────────────
    elapsed = time.perf_counter() - t0
    print()
    print(SEPARATOR)
    print("  EXECUTION SUMMARY")
    print(SEPARATOR)
    print(f"  Projects analysed          : {total:>10,}")
    print(f"  Duplicate pairs found      : {len(pairs_df):>10,}")
    if not pairs_df.empty:
        cross_mp_count = int((pairs_df["mp_a"] != pairs_df["mp_b"]).sum())
        same_c_count   = int((pairs_df.get("geo_relationship","") == "SAME_CONSTITUENCY").sum())
        print(f"  Cross-MP pairs             : {cross_mp_count:>10,}")
        print(f"  Same-constituency pairs    : {same_c_count:>10,}")
    for band in ["CRITICAL_DUPLICATE","HIGH_SIMILARITY"]:
        cnt = int(band_counts.get(band, 0))
        print(f"  {band:<35}: {cnt:>10,}  ({cnt/total*100:.1f}%)")
    print(f"  Execution time             : {elapsed:>10.2f}s")
    print(SEPARATOR)

    # ── 12. Top 10 highest-similarity pairs ───────────────────────────────────
    if not pairs_df.empty:
        print("\n  TOP 10 HIGHEST-SIMILARITY DUPLICATE PAIRS:")
        print(f"  {'Score':>6}  {'GeoRisk':<18}  {'Desc-A (truncated)':<50}  {'MP-A':<20}  {'MP-B'}")
        top10 = pairs_df.nlargest(10, "similarity_score")
        for _, row in top10.iterrows():
            desc_a = str(row.get("description_a",""))[:48]
            mp_a   = str(row.get("mp_a",""))[:18]
            mp_b   = str(row.get("mp_b",""))[:18]
            geo    = str(row.get("geo_risk_label",""))[:16]
            print(f"  {row['similarity_score']:>6.4f}  {geo:<18}  {desc_a:<50}  {mp_a:<20}  {mp_b}")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────
def inspect_project(project_id: str) -> None:
    """Print similarity info for a specific project_id."""
    df_sim = pd.read_csv(SIM_DATA_PATH, low_memory=False)
    row = df_sim[df_sim["project_id"] == project_id]
    if row.empty:
        print(f"Project ID not found: {project_id}")
        return
    print(f"\nProject: {project_id}")
    print(f"  Description : {row.iloc[0]['clean_description']}")
    print(f"  State       : {row.iloc[0]['state']}")
    print(f"  Constituency: {row.iloc[0]['constituency']}")
    print(f"  Precomputed similarity score: {row.iloc[0]['description_similarity_score']}")

    if os.path.isfile(PAIRS_PATH):
        pairs_df = pd.read_csv(PAIRS_PATH)
        related  = pairs_df[
            (pairs_df["project_id_a"] == project_id) |
            (pairs_df["project_id_b"] == project_id)
        ]
        if not related.empty:
            print(f"\n  Duplicate pairs involving this project ({len(related)} found):")
            for _, r in related.iterrows():
                other = r["project_id_b"] if r["project_id_a"] == project_id else r["project_id_a"]
                print(f"    Score={r['similarity_score']:.4f}  GeoRisk={r.get('geo_risk_label','')}  OtherProject={other}")
        else:
            print("  No duplicate pairs found for this project in current output.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MPLAD-Sentinel Similarity Engine Runner")
    parser.add_argument("--pair_threshold", type=float, default=0.85, help="Cosine similarity threshold for pairs (default=0.85)")
    parser.add_argument("--project_id",     type=str,   default=None, help="Inspect a specific project by ID")
    args = parser.parse_args()

    if args.project_id:
        inspect_project(args.project_id)
    else:
        run_pipeline(pair_threshold=args.pair_threshold)
