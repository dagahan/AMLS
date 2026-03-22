from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector, RuntimeSnapshot


def apply_node_score_increment(
    runtime: RuntimeSnapshot,
    node_score_increment: FloatVector,
) -> FloatVector:
    return np.asarray(
        runtime.node_scores + np.asarray(node_score_increment, dtype=np.float64),
        dtype=np.float64,
    )
