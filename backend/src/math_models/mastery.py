from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal


def build_beta_parameters(
    success_sum: Decimal,
    failure_sum: Decimal,
    alpha_0: Decimal,
    beta_0: Decimal,
) -> tuple[Decimal, Decimal]:
    return alpha_0 + success_sum, beta_0 + failure_sum


def calculate_posterior_mean(alpha: Decimal, beta: Decimal) -> Decimal:
    mastery = alpha / (alpha + beta)
    return min(max(mastery, Decimal("0")), Decimal("1"))


def extract_child_evidence(
    alpha: Decimal,
    beta: Decimal,
    alpha_0: Decimal,
    beta_0: Decimal,
) -> tuple[Decimal, Decimal]:
    return max(alpha - alpha_0, Decimal("0")), max(beta - beta_0, Decimal("0"))


def pool_weighted_evidence(
    weighted_evidence_items: Iterable[tuple[Decimal, Decimal, Decimal]],
) -> tuple[Decimal, Decimal]:
    pooled_success = Decimal("0")
    pooled_failure = Decimal("0")

    for weight, child_success, child_failure in weighted_evidence_items:
        pooled_success += weight * child_success
        pooled_failure += weight * child_failure

    return pooled_success, pooled_failure
