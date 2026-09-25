"""Round Figure Payment Analysis for MPLAD-Sentinel.

Detects artificial or suspicious round-number disbursements in project payments.
In public infrastructure procurement, genuine final payments almost always involve
statutory tax deductions (GST/TDS), labor cess, bill of quantities (BOQ) precision,
and retention money, resulting in non-round rupee figures. Exact round figures
(e.g., ₹50,000, ₹1,00,000, ₹5,00,000, ₹10,00,000) strongly correlate with
unverified advances, artificial lump-sum drawdowns, or structured extraction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Union, List


ROUND_MODULI_WEIGHTS = [
    (1000000.0, 1.00),   # Multiples of 10 Lakh (₹1,000,000)
    (500000.0, 0.85),    # Multiples of 5 Lakh (₹500,000)
    (200000.0, 0.75),    # Multiples of 2 Lakh (₹200,000)
    (100000.0, 0.65),    # Multiples of 1 Lakh (₹100,000)
    (50000.0, 0.50),     # Multiples of 50,000
    (25000.0, 0.35),     # Multiples of 25,000
    (10000.0, 0.25),     # Multiples of 10,000
    (5000.0, 0.15)       # Multiples of 5,000
]


def calculate_single_amount_roundness(amount: float) -> float:
    """Compute roundness score in [0.0, 1.0] for a single numeric payment amount."""
    if amount is None or np.isnan(amount) or np.isinf(amount) or amount <= 0:
        return 0.0

    # Ensure integer-level closeness (cents / floating point rounding)
    rounded_amt = round(float(amount))
    if abs(amount - rounded_amt) > 0.05:
        # Has significant paise/cents fraction, not round
        return 0.0

    # Small payments under 5000 are not considered suspiciously round
    if rounded_amt < 5000:
        return 0.0

    score = 0.0
    for mod, weight in ROUND_MODULI_WEIGHTS:
        if rounded_amt >= mod and (rounded_amt % mod == 0):
            score = max(score, weight)
            break

    return float(score)


def analyze_round_figure_payments(
    df: pd.DataFrame,
    total_col: str = "total_expenditure",
    avg_col: str = "average_payment",
    max_col: str = "maximum_payment"
) -> np.ndarray:
    """Vectorized calculation of round-payment indicator scores across a dataset.

    Parameters
    ----------
    df : pd.DataFrame
        Input DataFrame with payment columns.
    total_col : str
        Column name for total project expenditure.
    avg_col : str
        Column name for average payment amount.
    max_col : str
        Column name for maximum payment amount.

    Returns
    -------
    np.ndarray
        Array of round payment indicator scores bounded in [0.0, 1.0].
    """
    n = len(df)
    if n == 0:
        return np.array([], dtype=float)

    total_vals = pd.to_numeric(df.get(total_col, 0.0), errors="coerce").fillna(0.0).values
    avg_vals = pd.to_numeric(df.get(avg_col, 0.0), errors="coerce").fillna(0.0).values
    max_vals = pd.to_numeric(df.get(max_col, 0.0), errors="coerce").fillna(0.0).values

    # Replace infs
    total_vals = np.nan_to_num(total_vals, nan=0.0, posinf=0.0, neginf=0.0)
    avg_vals = np.nan_to_num(avg_vals, nan=0.0, posinf=0.0, neginf=0.0)
    max_vals = np.nan_to_num(max_vals, nan=0.0, posinf=0.0, neginf=0.0)

    indicators = np.zeros(n, dtype=float)

    for i in range(n):
        t_amt = total_vals[i]
        a_amt = avg_vals[i]
        m_amt = max_vals[i]

        if t_amt <= 0:
            indicators[i] = 0.0
            continue

        r_total = calculate_single_amount_roundness(t_amt)
        r_avg = calculate_single_amount_roundness(a_amt)
        r_max = calculate_single_amount_roundness(m_amt)

        # Composite roundness: prioritize average/max single transactions where available
        if a_amt > 0 and m_amt > 0:
            composite = 0.45 * r_avg + 0.35 * r_max + 0.20 * r_total
        elif m_amt > 0:
            composite = 0.55 * r_max + 0.45 * r_total
        else:
            composite = r_total

        indicators[i] = np.clip(composite, 0.0, 1.0)

    return np.round(indicators, 4)
