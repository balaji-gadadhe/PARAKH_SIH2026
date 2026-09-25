"""
analytics/similarity_engine/location_proximity.py
==================================================
Geographic risk classification for MPLAD-Sentinel similarity engine.

For any pair of projects, determines the geographic relationship:
  SAME_CONSTITUENCY        → Highest double-billing risk (same physical area)
  SAME_STATE_DIFF_CONST    → Medium risk (cross-constituency proposal sharing)
  DIFF_STATE               → Cross-MP proposal copying (lower, but suspicious if verbatim)
  UNKNOWN                  → Unable to resolve (null constituency / state)

Usage:
    from analytics.similarity_engine.location_proximity import LocationProximity
    lp = LocationProximity()
    result = lp.classify_pair("Gujarat", "SURAT", "Gujarat", "SURAT")
    # → "SAME_CONSTITUENCY"
"""
from __future__ import annotations
import re
import logging
import math
import pandas as pd
from typing import Optional

logger = logging.getLogger(__name__)

# Risk multipliers applied to the composite similarity score
LOCATION_RISK_WEIGHT = {
    "SAME_CONSTITUENCY":     1.0,   # Full weight — definite double-billing risk
    "SAME_STATE_DIFF_CONST": 0.7,   # High but could be state-wide scheme
    "DIFF_STATE":            0.4,   # Lower — more likely a copied template
    "UNKNOWN":               0.5,   # Conservative mid-weight
}

LOCATION_RISK_LABEL = {
    "SAME_CONSTITUENCY":     "CRITICAL_GEO",
    "SAME_STATE_DIFF_CONST": "HIGH_GEO",
    "DIFF_STATE":            "MEDIUM_GEO",
    "UNKNOWN":               "LOW_GEO",
}


class LocationProximity:
    """Classifies geographic relationship between project pairs."""

    @classmethod
    def verified_coordinate_rows(cls, location_df: Optional[pd.DataFrame]) -> pd.DataFrame:
        """Return only valid, explicitly real/verified, non-synthetic coordinates."""
        if location_df is None or location_df.empty:
            return pd.DataFrame(columns=["project_id", "latitude", "longitude"])

        required = {"project_id", "latitude", "longitude"}
        if not required.issubset(location_df.columns):
            return pd.DataFrame(columns=sorted(required))

        locations = location_df.copy()
        locations["latitude"] = pd.to_numeric(locations["latitude"], errors="coerce")
        locations["longitude"] = pd.to_numeric(locations["longitude"], errors="coerce")
        valid = (
            locations["latitude"].between(-90, 90)
            & locations["longitude"].between(-180, 180)
        )

        synthetic = pd.Series(False, index=locations.index)
        for column in ("location_is_synthetic", "is_synthetic", "demo_only"):
            if column in locations.columns:
                synthetic |= locations[column].astype("string").fillna("").str.lower().isin(
                    {"true", "1", "yes"}
                )

        source_is_real = pd.Series(False, index=locations.index)
        if "location_source" in locations.columns:
            source_is_real |= locations["location_source"].astype(str).str.lower().isin(
                {"real", "official_source", "geocoded_verified"}
            )
        if "is_verified" in locations.columns:
            source_is_real |= locations["is_verified"].astype("string").fillna("").str.lower().isin(
                {"true", "1", "yes"}
            )

        return locations[valid & source_is_real & ~synthetic].drop_duplicates(
            "project_id", keep="first"
        )

    @staticmethod
    def haversine_distance_m(
        latitude_a: object,
        longitude_a: object,
        latitude_b: object,
        longitude_b: object,
    ) -> Optional[float]:
        """Return great-circle distance in metres, or None for invalid coordinates."""
        try:
            lat_a, lon_a, lat_b, lon_b = map(
                float, (latitude_a, longitude_a, latitude_b, longitude_b)
            )
        except (TypeError, ValueError):
            return None

        if not (-90 <= lat_a <= 90 and -90 <= lat_b <= 90):
            return None
        if not (-180 <= lon_a <= 180 and -180 <= lon_b <= 180):
            return None

        earth_radius_m = 6_371_000
        lat_delta = math.radians(lat_b - lat_a)
        lon_delta = math.radians(lon_b - lon_a)
        a = (
            math.sin(lat_delta / 2) ** 2
            + math.cos(math.radians(lat_a))
            * math.cos(math.radians(lat_b))
            * math.sin(lon_delta / 2) ** 2
        )
        return round(2 * earth_radius_m * math.asin(math.sqrt(a)), 2)

    @staticmethod
    def distance_band(distance_m: Optional[float]) -> str:
        """Classify a valid GPS distance using the documented proximity bands."""
        if distance_m is None:
            return "GPS_UNAVAILABLE"
        if distance_m <= 100:
            return "SAME_SITE"
        if distance_m <= 1000:
            return "NEARBY"
        return "SEPARATE"

    @staticmethod
    def _normalise(s: Optional[str]) -> str:
        """Lowercase, strip special chars, collapse whitespace."""
        if not isinstance(s, str) or not s.strip():
            return "__unknown__"
        s = s.lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def classify_pair(
        self,
        state_a: Optional[str],
        constituency_a: Optional[str],
        state_b: Optional[str],
        constituency_b: Optional[str],
    ) -> str:
        """
        Return geographic relationship label for a project pair.

        Returns
        -------
        str
            One of: SAME_CONSTITUENCY, SAME_STATE_DIFF_CONST, DIFF_STATE, UNKNOWN
        """
        sa = self._normalise(state_a)
        sb = self._normalise(state_b)
        ca = self._normalise(constituency_a)
        cb = self._normalise(constituency_b)

        if ca == "__unknown__" or cb == "__unknown__":
            return "UNKNOWN"

        if ca == cb and sa == sb:
            return "SAME_CONSTITUENCY"

        if sa == sb:
            return "SAME_STATE_DIFF_CONST"

        if sa == "__unknown__" or sb == "__unknown__":
            return "UNKNOWN"

        return "DIFF_STATE"

    def get_risk_weight(self, geo_label: str) -> float:
        """Return the risk multiplier for a geographic relationship label."""
        return LOCATION_RISK_WEIGHT.get(geo_label, 0.5)

    def get_risk_label(self, geo_label: str) -> str:
        """Return the display risk label for a geographic relationship."""
        return LOCATION_RISK_LABEL.get(geo_label, "LOW_GEO")

    def annotate_pairs(
        self,
        pairs_df: pd.DataFrame,
        location_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Add geo_relationship, geo_risk_label, and geo_risk_weight columns
        to a pairs DataFrame produced by TextSimilarityEngine.find_duplicate_pairs().

        Parameters
        ----------
        pairs_df : pd.DataFrame
            Must have: state_a, constituency_a, state_b, constituency_b

        Returns
        -------
        pd.DataFrame with 3 additional columns.
        """
        if pairs_df.empty:
            pairs_df["geo_relationship"]  = pd.Series(dtype=str)
            pairs_df["geo_risk_label"]    = pd.Series(dtype=str)
            pairs_df["geo_risk_weight"]   = pd.Series(dtype=float)
            pairs_df["distance_m"]         = pd.Series(dtype=float)
            pairs_df["location_proximity"] = pd.Series(dtype=str)
            pairs_df["location_source"]    = pd.Series(dtype=str)
            return pairs_df

        geo_rels    = []
        geo_labels  = []
        geo_weights = []
        distances   = []
        proximity   = []
        sources     = []

        for _, row in pairs_df.iterrows():
            rel    = self.classify_pair(
                row.get("state_a"), row.get("constituency_a"),
                row.get("state_b"), row.get("constituency_b"),
            )
            geo_rels.append(rel)
            geo_labels.append(self.get_risk_label(rel))
            geo_weights.append(self.get_risk_weight(rel))

            # GPS is intentionally excluded from production similarity scoring.
            distances.append(None)
            proximity.append("GPS_NOT_USED")
            sources.append("administrative_area")

        pairs_df = pairs_df.copy()
        pairs_df["geo_relationship"]  = geo_rels
        pairs_df["geo_risk_label"]    = geo_labels
        pairs_df["geo_risk_weight"]   = geo_weights
        pairs_df["distance_m"]         = distances
        pairs_df["location_proximity"] = proximity
        pairs_df["location_source"]    = sources
        logger.info("Annotated %d pairs with geographic risk.", len(pairs_df))
        return pairs_df

    def build_project_geo_map(self, df: pd.DataFrame) -> dict:
        """
        Build a lookup {project_id: {"state": ..., "constituency": ...}}
        from the similarity dataset for fast access.
        """
        geo_map = {}
        for _, row in df.iterrows():
            geo_map[row["project_id"]] = {
                "state":        row.get("state", ""),
                "constituency": row.get("constituency", ""),
            }
        return geo_map
