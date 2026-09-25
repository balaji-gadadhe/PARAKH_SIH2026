"""Payment Anomaly Detection Module for MPLAD-Sentinel.

Components:
- round_figure_analysis: Round-number payment extraction detection
- frequency_analysis: Payment velocity, rapid succession, and transaction structuring
- unusual_payments: Budget overruns, single-payment concentration, and peer deviations
- payment_anomaly_detector: Comprehensive PaymentAnomalyDetector pipeline
"""

from analytics.payment_anomaly.round_figure_analysis import (
    analyze_round_figure_payments,
    calculate_single_amount_roundness
)
from analytics.payment_anomaly.frequency_analysis import analyze_payment_frequency
from analytics.payment_anomaly.unusual_payments import analyze_unusual_payments
from analytics.payment_anomaly.payment_anomaly_detector import (
    PaymentAnomalyDetector,
    run_payment_anomaly_pipeline
)

__all__ = [
    "analyze_round_figure_payments",
    "calculate_single_amount_roundness",
    "analyze_payment_frequency",
    "analyze_unusual_payments",
    "PaymentAnomalyDetector",
    "run_payment_anomaly_pipeline"
]
