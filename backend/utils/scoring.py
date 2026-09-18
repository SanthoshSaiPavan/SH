"""Weighted scoring helpers shared by Modules 2 and 3."""


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def normalize(value, min_val, max_val) -> float:
    """Normalize a value to the 0-1 range."""
    if max_val == min_val:
        return 0.5
    return clamp01((value - min_val) / (max_val - min_val))


def inverse_normalize(value, min_val, max_val) -> float:
    """Inverse normalize (lower is better, e.g. cost)."""
    return 1 - normalize(value, min_val, max_val)


def weighted_score(scores: dict, weights: dict) -> float:
    """Weighted composite of 0-1 component scores, returned on a 0-100 scale."""
    total = sum(scores[k] * weights[k] for k in scores)
    return round(max(0.0, min(100.0, total * 100)), 2)
