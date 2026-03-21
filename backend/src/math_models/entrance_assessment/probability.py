from __future__ import annotations

import numpy as np

from src.math_models.entrance_assessment.types import FloatVector


def calculate_state_probabilities(
    state_scores: FloatVector,
    temperature: float,
) -> tuple[FloatVector, float, int, float]:
    scaled_scores = np.asarray(state_scores * temperature, dtype=np.float64)
    score_shift = float(np.max(scaled_scores)) if scaled_scores.size > 0 else 0.0
    unnormalized = np.exp(scaled_scores - score_shift)
    total = float(unnormalized.sum())

    if total <= 0.0:
        raise ValueError("State probability normalization failed")

    probabilities = np.asarray(unnormalized / total, dtype=np.float64)
    positive_mask = probabilities > 0.0
    entropy = float(
        -np.sum(probabilities[positive_mask] * np.log2(probabilities[positive_mask]))
    )
    leader_state_index = int(np.argmax(probabilities))
    leader_state_probability = float(probabilities[leader_state_index])

    return probabilities, entropy, leader_state_index, leader_state_probability
