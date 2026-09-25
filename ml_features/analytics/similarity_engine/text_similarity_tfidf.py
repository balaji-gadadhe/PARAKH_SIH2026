"""
analytics/similarity_engine/text_similarity_tfidf.py
======================================================
TF-IDF Cosine Similarity Engine for MPLAD-Sentinel.

Detects:
  1. Verbatim / high-paraphrase copy-pasted work proposals.
  2. Cross-constituency / cross-MP identical project text.
  3. Applies a Generic Template Filter to suppress false positives
     for short 2-3 word ubiquitous phrases like "cc road", "solar light".
"""
from __future__ import annotations
import os, re, pickle, logging
from typing import List, Dict, Optional
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
GENERIC_TEMPLATES: set = {
    "construction of cc road", "cc road nirman", "solar light", "street lights",
    "muktidham nirman", "high mask light", "at public place", "purchase of books",
    "bus stand bus shed", "yatri prtikshalaya", "construction of community hall",
    "construction of stage for cultural activities", "new water tanker for panchayat",
    "ms pole with led semi high mast light", "as per attechment", "cc road",
    "drain nirman", "borewell", "bore well", "interlocking tiles", "hand pump",
}
MIN_SUSPICIOUS_LEN: int = 40
HIGH_SIMILARITY_THRESHOLD: float = 0.85
CRITICAL_SIMILARITY_THRESHOLD: float = 0.97
MODEL_CACHE_PATH: str = os.path.join(
    "analytics", "similarity_engine", "_cache", "tfidf_vectorizer.pkl"
)
CUSTOM_STOPWORDS: List[str] = [
    "the","a","an","and","or","but","of","to","in","for","with","at","by","from",
    "on","is","are","was","were","be","been","being","have","has","had","do",
    "does","did","will","would","shall","should","may","might","can","could",
    "this","that","these","those","it","its","work","works","project","scheme",
    "proposed","proposal","recommended","recommendation","under","near","via",
    "as","per","ka","ki","ke","se","ko","mein","hai","hain","aur",
    "nirman","karya","yojana","gram","nagar",
]

# ── TextSimilarityEngine ──────────────────────────────────────────────────────
class TextSimilarityEngine:
    """TF-IDF + cosine similarity duplicate-detection engine."""

    def __init__(
        self,
        min_suspicious_len: int = MIN_SUSPICIOUS_LEN,
        high_threshold: float = HIGH_SIMILARITY_THRESHOLD,
        critical_threshold: float = CRITICAL_SIMILARITY_THRESHOLD,
    ) -> None:
        self.min_suspicious_len = min_suspicious_len
        self.high_threshold = high_threshold
        self.critical_threshold = critical_threshold
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.tfidf_matrix = None
        self.project_ids: Optional[List[str]] = None
        self.descriptions: Optional[List[str]] = None

    # ── Helpers ────────────────────────────────────────────────────────────────
    @staticmethod
    def _clean(text: str) -> str:
        if not isinstance(text, str):
            return ""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _mp_name_from_project_id(project_id: object) -> str:
        """Recover the MP name from the composite project key when needed."""
        if not isinstance(project_id, str):
            return ""
        parts = project_id.split("|")
        return parts[1].strip() if len(parts) >= 4 else ""

    @staticmethod
    def is_generic_template(text: str) -> bool:
        if not isinstance(text, str):
            return True
        cleaned = text.lower().strip()
        if len(cleaned) < MIN_SUSPICIOUS_LEN:
            return True
        for t in GENERIC_TEMPLATES:
            if cleaned == t or cleaned.startswith(t + " "):
                return True
        return False

    @staticmethod
    def _specificity_weight(text: str) -> float:
        if not isinstance(text, str) or not text:
            return 0.0
        length = len(text.strip())
        if length < 20:  return 0.1
        if length < 40:  return 0.3
        if length < 80:  return 0.6
        return 1.0

    # ── Training ───────────────────────────────────────────────────────────────
    def fit(self, df: pd.DataFrame) -> "TextSimilarityEngine":
        logger.info("Fitting TF-IDF on %d descriptions...", len(df))
        self.project_ids = df["project_id"].tolist()
        raw = df["clean_description"].fillna("").tolist()
        self.descriptions = [self._clean(d) for d in raw]
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 3), sublinear_tf=True,
            min_df=2, max_df=0.80, analyzer="word",
            token_pattern=r"(?u)\b\w+\b",
            stop_words=CUSTOM_STOPWORDS, max_features=50_000,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.descriptions)
        self.tfidf_matrix = normalize(self.tfidf_matrix, norm="l2", copy=False)
        logger.info("Fitted. Vocab=%d, Shape=%s", len(self.vectorizer.vocabulary_), self.tfidf_matrix.shape)
        return self

    # ── Pair detection ─────────────────────────────────────────────────────────
    def find_duplicate_pairs(
        self,
        df: pd.DataFrame,
        similarity_threshold: float = None,
        max_pairs: int = 50_000,
        batch_size: int = 500,
    ) -> pd.DataFrame:
        """Return DataFrame of project pairs with cosine similarity >= threshold."""
        if self.tfidf_matrix is None:
            raise RuntimeError("Call .fit(df) first.")
        threshold = similarity_threshold if similarity_threshold is not None else self.high_threshold

        desc_map  = dict(zip(df["project_id"], df["clean_description"].fillna("")))
        state_map = dict(zip(df["project_id"], df.get("state", pd.Series(dtype=str)).fillna("")))
        const_map = dict(zip(df["project_id"], df.get("constituency", pd.Series(dtype=str)).fillna("")))
        if "mp_name" in df.columns:
            mp_map = dict(zip(df["project_id"], df["mp_name"].fillna("")))
        else:
            mp_map = {
                project_id: self._mp_name_from_project_id(project_id)
                for project_id in df["project_id"]
            }

        pairs: List[Dict] = []
        seen: set = set()
        n = len(self.project_ids)

        logger.info("Scanning %d projects for pairs with sim >= %.2f ...", n, threshold)

        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batch = self.tfidf_matrix[start:end]
            sim_mat = (batch @ self.tfidf_matrix.T).toarray()

            for local_i, global_i in enumerate(range(start, end)):
                sims = sim_mat[local_i]
                sims[global_i] = 0.0
                candidates = np.where(sims >= threshold)[0]

                for j in candidates:
                    if j <= global_i:
                        continue
                    key = (global_i, int(j))
                    if key in seen:
                        continue
                    seen.add(key)

                    pid_a = self.project_ids[global_i]
                    pid_b = self.project_ids[int(j)]
                    desc_a = desc_map.get(pid_a, "")
                    desc_b = desc_map.get(pid_b, "")
                    gen_a  = self.is_generic_template(desc_a)
                    gen_b  = self.is_generic_template(desc_b)
                    sw = (self._specificity_weight(desc_a) + self._specificity_weight(desc_b)) / 2.0

                    pairs.append({
                        "project_id_a":    pid_a,
                        "project_id_b":    pid_b,
                        "description_a":   desc_a[:200],
                        "description_b":   desc_b[:200],
                        "similarity_score": round(float(sims[j]), 4),
                        "exact_text_duplicate_flag": int(float(sims[j]) >= self.critical_threshold),
                        "high_text_similarity_flag": int(float(sims[j]) >= self.high_threshold),
                        "is_generic_a":    gen_a,
                        "is_generic_b":    gen_b,
                        "generic_template_pair_flag": int(gen_a or gen_b),
                        "both_specific":   not gen_a and not gen_b,
                        "specificity_weight": round(sw, 4),
                        "state_a":         state_map.get(pid_a, ""),
                        "state_b":         state_map.get(pid_b, ""),
                        "constituency_a":  const_map.get(pid_a, ""),
                        "constituency_b":  const_map.get(pid_b, ""),
                        "mp_a":            mp_map.get(pid_a, ""),
                        "mp_b":            mp_map.get(pid_b, ""),
                    })

                    if len(pairs) >= max_pairs:
                        logger.warning("max_pairs=%d reached, stopping early.", max_pairs)
                        df_out = pd.DataFrame(pairs).sort_values("similarity_score", ascending=False)
                        return df_out.reset_index(drop=True)

        df_out = pd.DataFrame(pairs)
        if not df_out.empty:
            df_out = df_out.sort_values("similarity_score", ascending=False)
        logger.info("Found %d pairs.", len(df_out))
        return df_out.reset_index(drop=True)

    # ── Per-project scoring ────────────────────────────────────────────────────
    def score_all(self, df: pd.DataFrame, batch_size: int = 500) -> Dict[str, float]:
        """Return {project_id: similarity_anomaly_score (0.0-1.0)} for all projects."""
        if self.tfidf_matrix is None:
            raise RuntimeError("Call .fit(df) first.")
        logger.info("Scoring %d projects...", len(df))

        project_ids  = df["project_id"].tolist()
        descriptions = df["clean_description"].fillna("").tolist()
        n = len(project_ids)
        scores: Dict[str, float] = {}

        for start in range(0, n, batch_size):
            end = min(start + batch_size, n)
            batch = self.tfidf_matrix[start:end]
            sim_mat = (batch @ self.tfidf_matrix.T).toarray()

            for local_i, global_i in enumerate(range(start, end)):
                sims = sim_mat[local_i].copy()
                sims[global_i] = 0.0
                pid  = project_ids[global_i]
                desc = descriptions[global_i]

                if self.is_generic_template(desc):
                    scores[pid] = 0.05
                    continue

                high_cnt     = int(np.sum(sims >= self.high_threshold))
                critical_cnt = int(np.sum(sims >= self.critical_threshold))
                raw          = min(1.0, (critical_cnt * 0.6 + high_cnt * 0.3) / 10.0)
                sw           = self._specificity_weight(desc)
                scores[pid]  = round(raw * sw, 4)

        return scores

    # ── Save / Load ────────────────────────────────────────────────────────────
    def save(self, path: str = MODEL_CACHE_PATH) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {"vectorizer": self.vectorizer, "tfidf_matrix": self.tfidf_matrix,
                 "project_ids": self.project_ids, "descriptions": self.descriptions}, f, protocol=4
            )
        logger.info("Model saved → %s", path)

    def load(self, path: str = MODEL_CACHE_PATH) -> "TextSimilarityEngine":
        with open(path, "rb") as f:
            p = pickle.load(f)
        self.vectorizer   = p["vectorizer"]
        self.tfidf_matrix = p["tfidf_matrix"]
        self.project_ids  = p["project_ids"]
        self.descriptions = p["descriptions"]
        logger.info("Model loaded ← %s  shape=%s", path, self.tfidf_matrix.shape)
        return self

    def transform_single(self, description: str) -> np.ndarray:
        if self.vectorizer is None:
            raise RuntimeError("Model not fitted.")
        vec = self.vectorizer.transform([self._clean(description)])
        vec = normalize(vec, norm="l2")
        return (self.tfidf_matrix @ vec.T).toarray().flatten()
