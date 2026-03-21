from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector, RuntimeSnapshot


def apply_state_increments(
    runtime: RuntimeSnapshot,
    state_increments: FloatVector,
) -> tuple[FloatVector, FloatVector, FloatVector]:
    next_alpha = runtime.alpha + np.maximum(state_increments, 0.0)
    next_beta = runtime.beta + np.maximum(-state_increments, 0.0)
    next_z = next_alpha - next_beta
    return next_alpha, next_beta, next_z
