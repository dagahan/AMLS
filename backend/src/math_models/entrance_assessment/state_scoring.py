from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector, StateArtifact


def calculate_state_increments(
    state_artifact: StateArtifact,
    support_profile: FloatVector,
    instance_difficulty_weight: float,
    epsilon: float,
) -> FloatVector:
    denominator = float(np.abs(support_profile).sum()) + epsilon
    raw_scores = state_artifact.state_sign_matrix.astype(np.float64) @ support_profile
    return np.asarray(
        float(instance_difficulty_weight) * (raw_scores / denominator),
        dtype=np.float64,
    )
