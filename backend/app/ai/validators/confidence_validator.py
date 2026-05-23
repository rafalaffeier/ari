"""
Validates AI confidence against tool risk level thresholds.
"""
THRESHOLDS = {
    "low":      0.70,
    "medium":   0.80,
    "high":     0.90,
    "critical": 0.95,
}


def is_confident_enough(confidence: float, risk_level: str) -> bool:
    threshold = THRESHOLDS.get(risk_level, 0.75)
    return confidence >= threshold


def required_threshold(risk_level: str) -> float:
    return THRESHOLDS.get(risk_level, 0.75)
