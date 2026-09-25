"""
case_ranking.py
===============
Case ranking and triage workflow engine.
Ranks projects for field investigators and exports prioritized investigation lists.
"""

from __future__ import annotations
import logging
from pathlib import Path
import pandas as pd
from typing import Dict, List, Optional, Any

import sys
WORKSPACE_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

try:
    from .prioritization import InvestigationPrioritizer
except ImportError:
    from analytics.investigation.prioritization import InvestigationPrioritizer

logger = logging.getLogger("Investigation.CaseRanking")


class CaseRanker:
    """Ranks and formats prioritized cases for field auditor triage."""

    @staticmethod
    def rank_cases(
        projects_df: pd.DataFrame,
        top_n: Optional[int] = None
    ) -> pd.DataFrame:
        """Assign ranking to cases and order by investigation urgency and priority score."""
        prio_df = InvestigationPrioritizer.prioritize_cases(projects_df)

        merged = projects_df.copy()
        for col in ["investigation_priority_score", "investigation_urgency", "audit_dispatch_recommended"]:
            if col in prio_df.columns:
                merged[col] = prio_df[col]

        # Order by priority score descending
        sorted_df = merged.sort_values("investigation_priority_score", ascending=False).reset_index(drop=True)
        sorted_df["investigation_rank"] = range(1, len(sorted_df) + 1)

        if top_n:
            sorted_df = sorted_df.head(top_n)

        logger.info(f"Ranked {len(sorted_df)} cases for investigation triage.")
        return sorted_df


def run_case_ranking_pipeline(
    input_csv: str = "ml_outputs/project_risk_results.csv",
    output_csv: str = "ml_outputs/investigation_prioritized_cases.csv",
    top_n: int = 1000
) -> pd.DataFrame:
    """Execute case ranking and save prioritized investigation list."""
    base = Path(__file__).resolve().parent.parent.parent
    in_path = base / input_csv
    out_path = base / output_csv

    logger.info(f"Loading data for case ranking from: {in_path}")
    df = pd.read_csv(in_path, low_memory=False)

    ranked_df = CaseRanker.rank_cases(df, top_n=top_n)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    ranked_df.to_csv(out_path, index=False)
    logger.info(f"Prioritized investigation cases saved to: {out_path}")
    return ranked_df


if __name__ == "__main__":
    run_case_ranking_pipeline()
