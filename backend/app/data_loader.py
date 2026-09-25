"""
data_loader.py
==============
Loads CSV data files into memory at FastAPI startup.
Read-only — no writes, no side effects beyond caching.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger("parakh.data_loader")

# Resolve paths relative to the repo root (SIH-2026/)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_RISK_RESULTS_PATH = _REPO_ROOT / "ml_features" / "ml_outputs" / "project_risk_results.csv"
# D-027: the 112 MB CSV exceeds GitHub's 100 MB limit, so the repo ships it
# gzipped (4.5 MB). pandas reads .csv.gz transparently — prefer the plain CSV
# when present (local regeneration), fall back to the committed .gz.
_RISK_RESULTS_GZ_PATH = _RISK_RESULTS_PATH.with_suffix(".csv.gz")
_MASTER_WORKS_PATH = _REPO_ROOT / "data" / "master" / "master_works.csv"
_MASTER_MP_PATH = _REPO_ROOT / "data" / "master" / "master_mp_summary.csv"
_AGENCY_PROFILES_PATH = _REPO_ROOT / "ml_features" / "ml_outputs" / "agency_profiles.csv"
_PROJECT_FEATURES_PATH = _REPO_ROOT / "ml_features" / "ml_input" / "project_features.csv"


class DataLoader:
    """In-memory CSV cache loaded once at startup."""

    def __init__(self) -> None:
        self.risk_results: Optional[pd.DataFrame] = None
        self.master_works: Optional[pd.DataFrame] = None
        self.master_mp: Optional[pd.DataFrame] = None
        self.agency_profiles: Optional[pd.DataFrame] = None
        self.project_features: Optional[pd.DataFrame] = None
        self._loaded = False

    def load_all(self) -> None:
        """Load all datasets. Raises FileNotFoundError if critical files are missing."""
        logger.info("Loading datasets into memory...")

        # Required: project_risk_results.csv (plain CSV or committed .csv.gz)
        if _RISK_RESULTS_PATH.exists():
            risk_results_path = _RISK_RESULTS_PATH
        elif _RISK_RESULTS_GZ_PATH.exists():
            risk_results_path = _RISK_RESULTS_GZ_PATH
        else:
            raise FileNotFoundError(
                f"Required file not found: {_RISK_RESULTS_PATH} (or {_RISK_RESULTS_GZ_PATH.name})\n"
                "The gzipped copy ships with the repo (D-027). If it is missing, restore it\n"
                "from git (git checkout -- ml_features/ml_outputs/project_risk_results.csv.gz)\n"
                "or regenerate it:\n"
                "  cd ml_features && python scripts/run_feature_integration.py"
            )
        self.risk_results = pd.read_csv(risk_results_path, low_memory=False)
        logger.info(f"Loaded risk_results: {len(self.risk_results):,} rows (from {risk_results_path.name})")

        # Optional: master_works (for extra project detail)
        if _MASTER_WORKS_PATH.exists():
            self.master_works = pd.read_csv(_MASTER_WORKS_PATH, low_memory=False)
            logger.info(f"Loaded master_works: {len(self.master_works):,} rows")
        else:
            logger.warning(f"master_works not found at {_MASTER_WORKS_PATH} — detail endpoint will use risk_results only")

        # Optional: master_mp_summary
        if _MASTER_MP_PATH.exists():
            self.master_mp = pd.read_csv(_MASTER_MP_PATH, low_memory=False)
            logger.info(f"Loaded master_mp: {len(self.master_mp):,} rows")
        else:
            logger.warning(f"master_mp not found at {_MASTER_MP_PATH} — MP endpoints will compute from risk_results")

        # Optional: agency_profiles
        if _AGENCY_PROFILES_PATH.exists():
            self.agency_profiles = pd.read_csv(_AGENCY_PROFILES_PATH, low_memory=False)
            logger.info(f"Loaded agency_profiles: {len(self.agency_profiles):,} rows")
        else:
            logger.warning(f"agency_profiles not found at {_AGENCY_PROFILES_PATH}")

        # Optional: project_features (investigation/financial/payment detail fields)
        if _PROJECT_FEATURES_PATH.exists():
            self.project_features = pd.read_csv(_PROJECT_FEATURES_PATH, low_memory=False)
            logger.info(f"Loaded project_features: {len(self.project_features):,} rows")
        else:
            logger.warning(f"project_features not found at {_PROJECT_FEATURES_PATH} — detail endpoint will serve reduced fields")

        self._loaded = True
        logger.info("All datasets loaded successfully.")

    @property
    def is_loaded(self) -> bool:
        return self._loaded


# Singleton — imported by routers and main.py
data_store = DataLoader()
