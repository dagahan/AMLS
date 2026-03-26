from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, TypedDict

from loguru import logger
from sqlalchemy import func, select

from src.storage.db.enums import EntranceTestResultNodeStatus
from src.models.alchemy import Problem, ProblemType, ProblemTypePrerequisite, Subtopic, Topic
from src.models.pydantic import (
    EntranceTestFinalResultResponse,
    EntranceTestResultGraphEdgeResponse,
    EntranceTestResultGraphNodeResponse,
    EntranceTestResultResponse,
    EntranceTestResultSubtopicSummaryResponse,
    EntranceTestResultTopicSummaryResponse,
    build_entrance_test_persisted_result_response,
    build_entrance_test_session_response,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.alchemy import EntranceTestSession


class ProblemTypeOwnershipCandidate(TypedDict):
    problem_type_id: uuid.UUID
    problem_type_name: str
    topic_id: uuid.UUID
    topic_name: str
    subtopic_id: uuid.UUID
    subtopic_name: str
    problem_count: int


class EntranceTestResultProjectionService:
    async def build_result(
        self,
        session: "AsyncSession",
        entrance_test_session: "EntranceTestSession",
    ) -> EntranceTestResultResponse:
        final_result = build_entrance_test_persisted_result_response(entrance_test_session)
        if final_result is None:
            raise ValueError("Entrance test result is not available")

        ownership_by_problem_type_id = await self._load_problem_type_ownership(session)
        active_problem_type_ids = set(ownership_by_problem_type_id)
        if not active_problem_type_ids:
            raise ValueError("Entrance test result graph does not have active problem types")

        self._log_missing_persisted_ids(
            final_result=final_result,
            active_problem_type_ids=active_problem_type_ids,
            session_id=entrance_test_session.id,
        )

        edges = await self._load_edges(
            session=session,
            active_problem_type_ids=active_problem_type_ids,
        )
        nodes = self._build_nodes(
            ownership_by_problem_type_id=ownership_by_problem_type_id,
            final_result=final_result,
        )
        topic_summaries = self._build_topic_summaries(nodes)
        subtopic_summaries = self._build_subtopic_summaries(nodes)

        logger.info(
            "Projected entrance test result: session_id={}, nodes={}, edges={}, topics={}, subtopics={}, learned={}, ready={}, frontier={}, locked={}",
            entrance_test_session.id,
            len(nodes),
            len(edges),
            len(topic_summaries),
            len(subtopic_summaries),
            sum(1 for node in nodes if node.status == EntranceTestResultNodeStatus.LEARNED),
            sum(1 for node in nodes if node.status == EntranceTestResultNodeStatus.READY),
            sum(1 for node in nodes if node.is_frontier),
            sum(1 for node in nodes if node.status == EntranceTestResultNodeStatus.LOCKED),
        )

        return EntranceTestResultResponse(
            session=build_entrance_test_session_response(entrance_test_session),
            final_result=final_result,
            nodes=nodes,
            edges=edges,
            topic_summaries=topic_summaries,
            subtopic_summaries=subtopic_summaries,
        )


    async def _load_problem_type_ownership(
        self,
        session: "AsyncSession",
    ) -> dict[uuid.UUID, ProblemTypeOwnershipCandidate]:
        result = await session.execute(
            select(
                ProblemType.id,
                ProblemType.name,
                Topic.id,
                Topic.name,
                Subtopic.id,
                Subtopic.name,
                func.count(Problem.id),
            )
            .join(Problem, Problem.problem_type_id == ProblemType.id)
            .join(Subtopic, Subtopic.id == Problem.subtopic_id)
            .join(Topic, Topic.id == Subtopic.topic_id)
            .group_by(
                ProblemType.id,
                ProblemType.name,
                Topic.id,
                Topic.name,
                Subtopic.id,
                Subtopic.name,
            )
        )

        candidates_by_problem_type_id: dict[uuid.UUID, list[ProblemTypeOwnershipCandidate]] = (
            defaultdict(list)
        )
        for (
            problem_type_id,
            problem_type_name,
            topic_id,
            topic_name,
            subtopic_id,
            subtopic_name,
            problem_count,
        ) in result.all():
            candidates_by_problem_type_id[problem_type_id].append(
                ProblemTypeOwnershipCandidate(
                    problem_type_id=problem_type_id,
                    problem_type_name=problem_type_name,
                    topic_id=topic_id,
                    topic_name=topic_name,
                    subtopic_id=subtopic_id,
                    subtopic_name=subtopic_name,
                    problem_count=int(problem_count),
                )
            )

        ownership_by_problem_type_id: dict[uuid.UUID, ProblemTypeOwnershipCandidate] = {}
        for problem_type_id, candidates in candidates_by_problem_type_id.items():
            sorted_candidates = sorted(
                candidates,
                key=lambda candidate: (
                    -candidate["problem_count"],
                    candidate["topic_name"],
                    candidate["subtopic_name"],
                    candidate["problem_type_name"],
                    str(candidate["topic_id"]),
                    str(candidate["subtopic_id"]),
                ),
            )
            chosen_candidate = sorted_candidates[0]
            if len(sorted_candidates) > 1:
                logger.warning(
                    "Problem type ownership is ambiguous, using deterministic choice: problem_type_id={}, problem_type_name={}, chosen_topic_id={}, chosen_subtopic_id={}, candidate_count={}",
                    chosen_candidate["problem_type_id"],
                    chosen_candidate["problem_type_name"],
                    chosen_candidate["topic_id"],
                    chosen_candidate["subtopic_id"],
                    len(sorted_candidates),
                )
            ownership_by_problem_type_id[problem_type_id] = chosen_candidate

        return ownership_by_problem_type_id


    async def _load_edges(
        self,
        session: "AsyncSession",
        active_problem_type_ids: set[uuid.UUID],
    ) -> list[EntranceTestResultGraphEdgeResponse]:
        result = await session.execute(
            select(
                ProblemTypePrerequisite.prerequisite_problem_type_id,
                ProblemTypePrerequisite.problem_type_id,
            )
            .where(
                ProblemTypePrerequisite.problem_type_id.in_(active_problem_type_ids),
                ProblemTypePrerequisite.prerequisite_problem_type_id.in_(
                    active_problem_type_ids
                ),
            )
        )

        return [
            EntranceTestResultGraphEdgeResponse(
                from_problem_type_id=from_problem_type_id,
                to_problem_type_id=to_problem_type_id,
            )
            for from_problem_type_id, to_problem_type_id in sorted(
                result.all(),
                key=lambda edge: (str(edge[0]), str(edge[1])),
            )
        ]


    def _build_nodes(
        self,
        ownership_by_problem_type_id: dict[uuid.UUID, ProblemTypeOwnershipCandidate],
        final_result: EntranceTestFinalResultResponse,
    ) -> list[EntranceTestResultGraphNodeResponse]:
        learned_ids = set(final_result.learned_problem_type_ids)
        inner_fringe_ids = set(final_result.inner_fringe_ids)
        outer_fringe_ids = set(final_result.outer_fringe_ids)
        ready_ids = outer_fringe_ids - learned_ids

        nodes: list[EntranceTestResultGraphNodeResponse] = []
        for problem_type_id, ownership in ownership_by_problem_type_id.items():
            status = EntranceTestResultNodeStatus.LOCKED
            if problem_type_id in learned_ids:
                status = EntranceTestResultNodeStatus.LEARNED
            elif problem_type_id in ready_ids:
                status = EntranceTestResultNodeStatus.READY

            nodes.append(
                EntranceTestResultGraphNodeResponse(
                    id=problem_type_id,
                    name=ownership["problem_type_name"],
                    topic_id=ownership["topic_id"],
                    topic_name=ownership["topic_name"],
                    subtopic_id=ownership["subtopic_id"],
                    subtopic_name=ownership["subtopic_name"],
                    status=status,
                    is_frontier=problem_type_id in learned_ids
                    and problem_type_id in inner_fringe_ids,
                )
            )

        return sorted(
            nodes,
            key=lambda node: (
                node.topic_name,
                node.subtopic_name,
                node.name,
                str(node.id),
            ),
        )


    def _build_topic_summaries(
        self,
        nodes: list[EntranceTestResultGraphNodeResponse],
    ) -> list[EntranceTestResultTopicSummaryResponse]:
        summary_by_topic_id: dict[uuid.UUID, EntranceTestResultTopicSummaryResponse] = {}

        for node in nodes:
            summary = summary_by_topic_id.get(node.topic_id)
            if summary is None:
                summary = EntranceTestResultTopicSummaryResponse(
                    topic_id=node.topic_id,
                    topic_name=node.topic_name,
                    total_problem_types=0,
                    learned_count=0,
                    ready_count=0,
                    frontier_count=0,
                    locked_count=0,
                )
                summary_by_topic_id[node.topic_id] = summary

            summary.total_problem_types += 1
            if node.status == EntranceTestResultNodeStatus.LEARNED:
                summary.learned_count += 1
            elif node.status == EntranceTestResultNodeStatus.READY:
                summary.ready_count += 1
            else:
                summary.locked_count += 1

            if node.is_frontier:
                summary.frontier_count += 1

        return sorted(
            summary_by_topic_id.values(),
            key=lambda summary: (summary.topic_name, str(summary.topic_id)),
        )


    def _build_subtopic_summaries(
        self,
        nodes: list[EntranceTestResultGraphNodeResponse],
    ) -> list[EntranceTestResultSubtopicSummaryResponse]:
        summary_by_subtopic_id: dict[
            uuid.UUID,
            EntranceTestResultSubtopicSummaryResponse,
        ] = {}

        for node in nodes:
            summary = summary_by_subtopic_id.get(node.subtopic_id)
            if summary is None:
                summary = EntranceTestResultSubtopicSummaryResponse(
                    subtopic_id=node.subtopic_id,
                    subtopic_name=node.subtopic_name,
                    topic_id=node.topic_id,
                    topic_name=node.topic_name,
                    total_problem_types=0,
                    learned_count=0,
                    ready_count=0,
                    frontier_count=0,
                    locked_count=0,
                )
                summary_by_subtopic_id[node.subtopic_id] = summary

            summary.total_problem_types += 1
            if node.status == EntranceTestResultNodeStatus.LEARNED:
                summary.learned_count += 1
            elif node.status == EntranceTestResultNodeStatus.READY:
                summary.ready_count += 1
            else:
                summary.locked_count += 1

            if node.is_frontier:
                summary.frontier_count += 1

        return sorted(
            summary_by_subtopic_id.values(),
            key=lambda summary: (
                summary.topic_name,
                summary.subtopic_name,
                str(summary.subtopic_id),
            ),
        )


    def _log_missing_persisted_ids(
        self,
        final_result: EntranceTestFinalResultResponse,
        active_problem_type_ids: set[uuid.UUID],
        session_id: uuid.UUID,
    ) -> None:
        persisted_problem_type_ids = (
            set(final_result.learned_problem_type_ids)
            | set(final_result.inner_fringe_ids)
            | set(final_result.outer_fringe_ids)
        )
        missing_problem_type_ids = sorted(
            persisted_problem_type_ids - active_problem_type_ids,
            key=str,
        )
        if missing_problem_type_ids:
            logger.warning(
                "Entrance test projection skipped persisted problem types that are absent from the active graph: session_id={}, missing_problem_type_ids={}",
                session_id,
                missing_problem_type_ids,
            )
