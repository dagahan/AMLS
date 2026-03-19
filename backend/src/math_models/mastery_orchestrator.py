from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from src.math_models.mastery import (
    build_beta_parameters,
    calculate_posterior_mean,
    extract_child_evidence,
    pool_weighted_evidence,
)
from src.models.pydantic.mastery import (
    MasteryAggregationSnapshot,
    MasteryBetaValue,
    MasteryEvidenceValue,
    MasteryOverviewCache,
    TopicSubtopicWeightValue,
)


def build_mastery_overview_cache(
    snapshot: MasteryAggregationSnapshot,
    alpha_0: Decimal,
    beta_0: Decimal,
) -> MasteryOverviewCache:
    skill_betas = build_leaf_betas(
        entity_ids=snapshot.skill_ids,
        evidence_values=snapshot.skill_evidence,
        alpha_0=alpha_0,
        beta_0=beta_0,
    )
    subtopic_betas = build_leaf_betas(
        entity_ids=snapshot.subtopic_ids,
        evidence_values=snapshot.subtopic_evidence,
        alpha_0=alpha_0,
        beta_0=beta_0,
    )
    topic_betas = build_topic_betas(
        topic_ids=snapshot.topic_ids,
        subtopic_betas=subtopic_betas,
        topic_links=snapshot.topic_links,
        alpha_0=alpha_0,
        beta_0=beta_0,
    )

    return MasteryOverviewCache(
        skills=skill_betas,
        subtopics=subtopic_betas,
        topics=topic_betas,
    )


def build_leaf_betas(
    entity_ids: list[UUID],
    evidence_values: list[MasteryEvidenceValue],
    alpha_0: Decimal,
    beta_0: Decimal,
) -> list[MasteryBetaValue]:
    betas_by_id = {
        entity_id: build_prior_beta_value(entity_id, alpha_0, beta_0)
        for entity_id in entity_ids
    }

    for evidence_value in evidence_values:
        betas_by_id[evidence_value.id] = build_beta_value(
            entity_id=evidence_value.id,
            success_sum=evidence_value.success_sum,
            failure_sum=evidence_value.failure_sum,
            alpha_0=alpha_0,
            beta_0=beta_0,
        )

    return sort_beta_values(betas_by_id)


def build_topic_betas(
    topic_ids: list[UUID],
    subtopic_betas: list[MasteryBetaValue],
    topic_links: list[TopicSubtopicWeightValue],
    alpha_0: Decimal,
    beta_0: Decimal,
) -> list[MasteryBetaValue]:
    subtopic_betas_by_id = {item.id: item for item in subtopic_betas}
    links_by_topic_id: dict[UUID, list[tuple[UUID, Decimal]]] = {}

    for topic_link in topic_links:
        links_by_topic_id.setdefault(topic_link.topic_id, []).append(
            (topic_link.subtopic_id, topic_link.weight)
        )

    betas_by_id = {
        topic_id: build_prior_beta_value(topic_id, alpha_0, beta_0)
        for topic_id in topic_ids
    }

    for topic_id in topic_ids:
        weighted_evidence_items: list[tuple[Decimal, Decimal, Decimal]] = []
        for subtopic_id, weight in links_by_topic_id.get(topic_id, []):
            subtopic_beta = subtopic_betas_by_id.get(subtopic_id)
            if subtopic_beta is None:
                subtopic_beta = build_prior_beta_value(subtopic_id, alpha_0, beta_0)
            child_success, child_failure = extract_child_evidence(
                alpha=subtopic_beta.alpha,
                beta=subtopic_beta.beta,
                alpha_0=alpha_0,
                beta_0=beta_0,
            )
            weighted_evidence_items.append((weight, child_success, child_failure))

        pooled_success, pooled_failure = pool_weighted_evidence(weighted_evidence_items)
        betas_by_id[topic_id] = build_beta_value(
            entity_id=topic_id,
            success_sum=pooled_success,
            failure_sum=pooled_failure,
            alpha_0=alpha_0,
            beta_0=beta_0,
        )

    return sort_beta_values(betas_by_id)


def build_prior_beta_value(
    entity_id: UUID,
    alpha_0: Decimal,
    beta_0: Decimal,
) -> MasteryBetaValue:
    return MasteryBetaValue(
        id=entity_id,
        alpha=alpha_0,
        beta=beta_0,
        mastery=calculate_posterior_mean(alpha_0, beta_0),
    )


def build_beta_value(
    entity_id: UUID,
    success_sum: Decimal,
    failure_sum: Decimal,
    alpha_0: Decimal,
    beta_0: Decimal,
) -> MasteryBetaValue:
    alpha, beta = build_beta_parameters(
        success_sum=success_sum,
        failure_sum=failure_sum,
        alpha_0=alpha_0,
        beta_0=beta_0,
    )
    return MasteryBetaValue(
        id=entity_id,
        alpha=alpha,
        beta=beta,
        mastery=calculate_posterior_mean(alpha, beta),
    )


def sort_beta_values(beta_values_by_id: dict[UUID, MasteryBetaValue]) -> list[MasteryBetaValue]:
    return [
        beta_values_by_id[entity_id]
        for entity_id in sorted(beta_values_by_id, key=str)
    ]
