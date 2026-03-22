from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector


def calculate_node_score_increment(
    support_profile: FloatVector,
    instance_difficulty_weight: float,
    epsilon: float,
) -> FloatVector:
    denominator = float(np.abs(support_profile).sum()) + epsilon
    normalized_profile = (
        (2.0 * float(instance_difficulty_weight))
        * np.asarray(support_profile, dtype=np.float64)
        / denominator
    )
    return np.asarray(normalized_profile, dtype=np.float64)
