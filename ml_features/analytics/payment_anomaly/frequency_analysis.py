"""Payment Frequency and Velocity Analysis for MPLAD-Sentinel.

Evaluates payment frequency, rapid transaction bursts, and transaction structuring.
Patterns identified:
1. High Payment Velocity: Multiple disbursements occurring in unusually close succession.
2. Transaction Structuring (Smurfing): Breaking payments into an abnormally large count
   of smaller tranches to evade scrutiny or statutory review thresholds.
3. Pending Transaction Friction: Disputed or stalled pending payment attempts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def analyze_payment_frequency(
    df: pd.DataFrame,
    freq_col: str = "payment_frequency",
    count_col: str = "payment_count",
    pending_col: str = "pending_payment_count"
) -> np.ndarray:
    """Compute payment frequency and velocity anomaly indicator bounded in [0.0, 1.0].

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame containing frequency and payment count columns.
    freq_col : str
        Column for transaction frequency (payments per day/interval).
    count_col : str
        Column for total payment count.
    pending_col : str
        Column for count of pending payment transactions.

    Returns
    -------
    np.ndarray
        Array of frequency anomaly indicator scores in [0.0, 1.0].
    """
    n = len(df)
    if n == 0:
        return np.array([], dtype=float)

    freq_vals = pd.to_numeric(df.get(freq_col, 0.0), errors="coerce").fillna(0.0).values
    count_vals = pd.to_numeric(df.get(count_col, 0), errors="coerce").fillna(0).values
    pending_vals = pd.to_numeric(df.get(pending_col, 0), errors="coerce").fillna(0).values

    # Clean Infs
    freq_vals = np.nan_to_num(freq_vals, nan=0.0, posinf=10.0, neginf=0.0)
    count_vals = np.nan_to_num(count_vals, nan=0, posinf=100, neginf=0)
    pending_vals = np.nan_to_num(pending_vals, nan=0, posinf=20, neginf=0)

    indicators = np.zeros(n, dtype=float)

    for i in range(n):
        freq = float(freq_vals[i])
        cnt = float(count_vals[i])
        pending = float(pending_vals[i])

        if cnt <= 0 and pending <= 0:
            indicators[i] = 0.0
            continue

        # 1. Velocity Score:
        # Typical MPLADS payment frequency has median ~0.08 (~1 payment every 12 days).
        # Frequencies > 0.5 (payment every 2 days) or > 1.0 (multiple per day) are extreme.
        # Sigmoid centered around 0.25
        if freq > 0:
            velocity_score = 1.0 / (1.0 + np.exp(-5.0 * (freq - 0.25)))
        else:
            velocity_score = 0.0

        # 2. Structuring / Count Score:
        # Typical project has 1 to 4 payments.
        # Projects with 10-85 payments represent transaction churning / structuring.
        if cnt >= 20:
            count_score = 1.0
        elif cnt >= 10:
            count_score = 0.70 + (cnt - 10) * 0.03
        elif cnt >= 5:
            count_score = 0.30 + (cnt - 5) * 0.08
        else:
            count_score = 0.05 if cnt > 0 else 0.0

        # 3. Pending friction score:
        if pending >= 5:
            pending_score = 0.85
        elif pending >= 2:
            pending_score = 0.50
        elif pending >= 1:
            pending_score = 0.25
        else:
            pending_score = 0.0

        # Combine components
        composite = max(velocity_score, count_score * 0.9, pending_score * 0.8)
        # If both high frequency and high count exist, escalate risk
        if velocity_score > 0.6 and count_score > 0.5:
            composite = min(1.0, composite + 0.15)

        indicators[i] = np.clip(composite, 0.0, 1.0)

    return np.round(indicators, 4)
