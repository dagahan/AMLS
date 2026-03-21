from __future__ import annotations

def calculate_temperature(
    previous_entropy: float,
    initial_entropy: float,
    temperature_sharpening: float,
) -> float:
    if initial_entropy <= 0.0:
        return 1.0

    certainty_progress = 1.0 - (previous_entropy / initial_entropy)
    certainty_progress = max(0.0, min(1.0, certainty_progress))
    return 1.0 + (temperature_sharpening * certainty_progress)
