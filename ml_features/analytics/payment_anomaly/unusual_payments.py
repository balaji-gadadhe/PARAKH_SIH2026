"""Unusual Payments Magnitude and Budget Discrepancy Analysis for MPLAD-Sentinel.

Evaluates:
1. Unusually Large Individual Payments: Transactions of exorbitant size.
2. Budget Payment Ratio: Project expenditure exceeding sanctioned allocation (overrun).
3. Single Payment Concentration: Lump-sum drawdowns consuming disproportionate share of budget.
4. Peer Payment Deviation: Discrepancy relative to peer project benchmarks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Tuple


def analyze_unusual_payments(
    df: pd.DataFrame,
    total_col: str = "total_expenditure",
    rec_col: str = "recommended_amount",
    max_col: str = "maximum_payment",
    peer_col: str = "peer_median_cost"
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute budget payment ratios, peer payment deviations, and magnitude risk scores.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame.
    total_col : str
        Column name for total payments / expenditure.
    rec_col : str
        Column name for recommended sanctioned budget.
    max_col : str
        Column name for maximum single payment.
    peer_col : str
        Column name for peer median cost benchmark.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, np.ndarray]
        - budget_payment_ratios: Array of expenditure-to-budget ratios.
        - peer_payment_deviations: Array of percentage deviations from peer median.
        - magnitude_risk_scores: Calibrated risk scores in [0.0, 1.0].
    """
    n = len(df)
    if n == 0:
        return np.array([]), np.array([]), np.array([])

    tot_vals = pd.to_numeric(df.get(total_col, 0.0), errors="coerce").fillna(0.0).values
    rec_vals = pd.to_numeric(df.get(rec_col, 0.0), errors="coerce").fillna(0.0).values
    max_vals = pd.to_numeric(df.get(max_col, 0.0), errors="coerce").fillna(0.0).values
    peer_vals = pd.to_numeric(df.get(peer_col, 500000.0), errors="coerce").fillna(500000.0).values

    # Clean in advance
    tot_vals = np.nan_to_num(tot_vals, nan=0.0, posinf=0.0, neginf=0.0)
    rec_vals = np.nan_to_num(rec_vals, nan=0.0, posinf=0.0, neginf=0.0)
    max_vals = np.nan_to_num(max_vals, nan=0.0, posinf=0.0, neginf=0.0)
    peer_vals = np.nan_to_num(peer_vals, nan=500000.0, posinf=500000.0, neginf=500000.0)

    # 1. Budget Payment Ratio (avoid division by zero)
    safe_rec = np.where(rec_vals > 0, rec_vals, 1.0)
    budget_ratios = np.where(tot_vals > 0, tot_vals / safe_rec, 0.0)
    # Clip extreme ratios to avoid floating point overflow
    budget_ratios = np.clip(budget_ratios, 0.0, 1000.0)

    # 2. Peer Payment Deviation (percentage deviation vs peer median)
    safe_peer = np.where(peer_vals > 0, peer_vals, 500000.0)
    peer_deviations = np.where(tot_vals > 0, ((tot_vals - safe_peer) / safe_peer) * 100.0, 0.0)
    peer_deviations = np.clip(peer_deviations, -100.0, 50000.0)

    # 3. Magnitude Risk Score
    magnitude_scores = np.zeros(n, dtype=float)

    for i in range(n):
        tot = tot_vals[i]
        b_ratio = budget_ratios[i]
        p_dev = peer_deviations[i]
        m_amt = max_vals[i]

        if tot <= 0:
            magnitude_scores[i] = 0.0
            continue

        # Overrun risk: ratio > 1.05 is suspicious, ratio > 2.0 is extreme
        if b_ratio > 2.0:
            overrun_risk = 1.0
        elif b_ratio > 1.05:
            overrun_risk = 0.50 + (b_ratio - 1.05) * 0.40
        else:
            overrun_risk = 0.0

        # Peer deviation risk: positive deviations above +200%
        if p_dev >= 500.0:
            peer_risk = 0.90
        elif p_dev >= 200.0:
            peer_risk = 0.60
        elif p_dev >= 100.0:
            peer_risk = 0.35
        else:
            peer_risk = 0.0

        # Large individual payment risk (> ₹25 lakh, ₹50 lakh, ₹1 crore)
        if m_amt >= 50000000.0:  # ₹5 Crore
            large_pmt_risk = 1.0
        elif m_amt >= 10000000.0: # ₹1 Crore
            large_pmt_risk = 0.85
        elif m_amt >= 5000000.0:  # ₹50 Lakh
            large_pmt_risk = 0.65
        elif m_amt >= 2500000.0:  # ₹25 Lakh
            large_pmt_risk = 0.40
        else:
            large_pmt_risk = 0.0

        score = max(overrun_risk, peer_risk * 0.85, large_pmt_risk * 0.9)
        magnitude_scores[i] = np.clip(score, 0.0, 1.0)

    return np.round(budget_ratios, 4), np.round(peer_deviations, 2), np.round(magnitude_scores, 4)
