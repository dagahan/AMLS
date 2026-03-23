from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector


def calculate_node_score_increment(
    support_profile: FloatVector,
    instance_difficulty_weight: float,
    epsilon: float,
) -> FloatVector:
    _ = epsilon
    return np.asarray(
        np.asarray(support_profile, dtype=np.float64)
        * float(instance_difficulty_weight),
        dtype=np.float64,
    )
