from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select

from src.core.utils import EnvTools
from src.db.enums import ProblemAnswerOptionType
from src.math_models.entrance_assessment import (
    Outcome,
    apply_answer_step,
    build_final_result,
    build_graph_artifact,
    build_state_artifact,
    initialize_runtime,
    select_next_problem_type,
    should_stop,
)
from src.math_models.entrance_assessment.types import GraphArtifact
from src.models.alchemy import Difficulty, Problem, ProblemAnswerOption, ProblemType, ProblemTypePrerequisite, ResponseEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class EntranceAssessmentService:
    def __init__(self) -> None:
        self.i_dont_know_scalar = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_I_DONT_KNOW_SCALAR")
        )
        self.ancestor_support_correct = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_CORRECT")
        )
        self.ancestor_support_wrong = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_SUPPORT_WRONG")
        )
        self.descendant_support_correct = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_CORRECT")
        )
        self.descendant_support_wrong = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_SUPPORT_WRONG")
        )
        self.ancestor_decay = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ANCESTOR_DECAY")
        )
        self.descendant_decay = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_DESCENDANT_DECAY")
        )
        self.branch_penalty_exponent = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_BRANCH_PENALTY_EXPONENT")
        )
        self.temperature_sharpening = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_TEMPERATURE_SHARPENING")
        )
        self.entropy_stop = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_ENTROPY_STOP")
        )
        self.utility_stop = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_UTILITY_STOP")
        )
        self.leader_probability_stop = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_LEADER_PROBABILITY_STOP")
        )
        self.max_questions = int(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_MAX_QUESTIONS")
        )
        self.epsilon = float(
            EnvTools.required_load_env_var("ENTRANCE_ASSESSMENT_EPSILON")
        )
        logger.info(
            "Loaded entrance assessment parameters: i_dont_know_scalar={}, ancestor_support_correct={}, ancestor_support_wrong={}, descendant_support_correct={}, descendant_support_wrong={}, ancestor_decay={}, descendant_decay={}, branch_penalty_exponent={}, temperature_sharpening={}, entropy_stop={}, utility_stop={}, leader_probability_stop={}, max_questions={}, epsilon={}",
            self.i_dont_know_scalar,
            self.ancestor_support_correct,
            self.ancestor_support_wrong,
            self.descendant_support_correct,
            self.descendant_support_wrong,
            self.ancestor_decay,
            self.descendant_decay,
            self.branch_penalty_exponent,
            self.temperature_sharpening,
            self.entropy_stop,
            self.utility_stop,
            self.leader_probability_stop,
            self.max_questions,
            self.epsilon,
        )


    async def select_next_problem_id(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
    ) -> uuid.UUID | None:
        available_problem_ids_by_type = await self._load_available_problem_ids_by_type(
            session,
            entrance_test_session_id,
        )
        if not available_problem_ids_by_type:
            logger.info(
                "Entrance assessment has no available problems for session {}",
                entrance_test_session_id,
            )
            return None

        graph_artifact = await self._load_graph_artifact(session)
        state_artifact = build_state_artifact(graph_artifact)
        runtime = initialize_runtime(state_artifact)
        answer_steps = await self._load_answer_steps(session, entrance_test_session_id)

        if not answer_steps:
            initial_selection = select_next_problem_type(
                graph_artifact=graph_artifact,
                state_artifact=state_artifact,
                runtime=runtime,
                available_problem_type_indices=self._resolve_available_problem_type_indices(
                    graph_artifact=graph_artifact,
                    available_problem_ids_by_type=available_problem_ids_by_type,
                ),
            )
            stop, stop_reason = should_stop(
                runtime=runtime,
                selection=initial_selection,
                entropy_stop=self.entropy_stop,
                utility_stop=self.utility_stop,
                leader_probability_stop=self.leader_probability_stop,
                max_questions=self.max_questions,
            )
            logger.debug(
                "Entrance assessment initial selection for session {}: entropy={}, utility={}, selected_problem_type_id={}, stop_reason={}",
                entrance_test_session_id,
                runtime.current_entropy,
                initial_selection.max_utility,
                initial_selection.problem_type_id,
                stop_reason,
            )
            if stop or initial_selection.problem_type_id is None:
                return None
            return available_problem_ids_by_type[initial_selection.problem_type_id][0]

        last_step = None
        available_problem_type_ids = set(available_problem_ids_by_type)

        for problem_type_id, outcome, difficulty_weight in answer_steps:
            logger.debug(
                "Replaying entrance assessment answer for session {}: problem_type_id={}, outcome={}, difficulty_weight={}",
                entrance_test_session_id,
                problem_type_id,
                outcome,
                difficulty_weight,
            )
            last_step = apply_answer_step(
                graph_artifact=graph_artifact,
                state_artifact=state_artifact,
                runtime=runtime,
                answered_problem_type_id=problem_type_id,
                outcome=outcome,
                instance_difficulty_weight=difficulty_weight,
                i_dont_know_scalar=self.i_dont_know_scalar,
                ancestor_support_correct=self.ancestor_support_correct,
                ancestor_support_wrong=self.ancestor_support_wrong,
                descendant_support_correct=self.descendant_support_correct,
                descendant_support_wrong=self.descendant_support_wrong,
                ancestor_decay=self.ancestor_decay,
                descendant_decay=self.descendant_decay,
                temperature_sharpening=self.temperature_sharpening,
                entropy_stop=self.entropy_stop,
                utility_stop=self.utility_stop,
                leader_probability_stop=self.leader_probability_stop,
                max_questions=self.max_questions,
                epsilon=self.epsilon,
                available_problem_type_ids=available_problem_type_ids,
            )
            runtime = last_step.runtime

        if last_step is None:
            return None

        logger.info(
            "Entrance assessment runtime for session {}: asked={}, entropy={}, leader_probability={}, next_problem_type_id={}, utility={}, stop_reason={}",
            entrance_test_session_id,
            len(runtime.asked_problem_type_indices),
            runtime.current_entropy,
            runtime.leader_state_probability,
            last_step.selection.problem_type_id,
            last_step.selection.max_utility,
            last_step.stop_reason,
        )

        if last_step.should_stop or last_step.selection.problem_type_id is None:
            final_result = build_final_result(
                graph_artifact=graph_artifact,
                state_artifact=state_artifact,
                runtime=runtime,
            )
            logger.info(
                "Entrance assessment final result for session {}: state_index={}, probability={}, learned_ids={}, inner_fringe_ids={}, outer_fringe_ids={}",
                entrance_test_session_id,
                final_result.state_index,
                final_result.state_probability,
                final_result.learned_problem_type_ids,
                final_result.inner_fringe_ids,
                final_result.outer_fringe_ids,
            )
            return None

        next_problem_type_id = last_step.selection.problem_type_id
        next_problem_ids = available_problem_ids_by_type.get(next_problem_type_id)
        if not next_problem_ids:
            logger.warning(
                "Entrance assessment selected unavailable problem type {} for session {}",
                next_problem_type_id,
                entrance_test_session_id,
            )
            return None

        logger.info(
            "Entrance assessment selected next problem for session {}: problem_type_id={}, problem_id={}",
            entrance_test_session_id,
            next_problem_type_id,
            next_problem_ids[0],
        )

        return next_problem_ids[0]


    async def _load_graph_artifact(self, session: "AsyncSession") -> GraphArtifact:
        problem_type_ids_result = await session.execute(
            select(ProblemType.id).order_by(ProblemType.created_at, ProblemType.id)
        )
        problem_type_ids = tuple(problem_type_ids_result.scalars().all())
        prerequisite_edges_result = await session.execute(
            select(
                ProblemTypePrerequisite.problem_type_id,
                ProblemTypePrerequisite.prerequisite_problem_type_id,
            )
        )
        prerequisite_edges = tuple(
            (problem_type_id, prerequisite_problem_type_id)
            for problem_type_id, prerequisite_problem_type_id in prerequisite_edges_result.all()
        )

        logger.debug(
            "Loaded entrance assessment graph: problem_types={}, prerequisite_edges={}",
            len(problem_type_ids),
            len(prerequisite_edges),
        )

        return build_graph_artifact(
            problem_type_ids=problem_type_ids,
            prerequisite_edges=prerequisite_edges,
            branch_penalty_exponent=self.branch_penalty_exponent,
        )


    async def _load_available_problem_ids_by_type(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        answered_problem_ids = select(ResponseEvent.problem_id).where(
            ResponseEvent.entrance_test_session_id == entrance_test_session_id
        )
        result = await session.execute(
            select(Problem.id, Problem.problem_type_id)
            .where(Problem.id.not_in(answered_problem_ids))
            .order_by(Problem.created_at, Problem.id)
        )

        available_problem_ids_by_type: dict[uuid.UUID, list[uuid.UUID]] = {}
        for problem_id, problem_type_id in result.all():
            available_problem_ids_by_type.setdefault(problem_type_id, []).append(problem_id)

        logger.debug(
            "Loaded available entrance assessment problems for session {}: problem_types={}, problems={}",
            entrance_test_session_id,
            len(available_problem_ids_by_type),
            sum(len(problem_ids) for problem_ids in available_problem_ids_by_type.values()),
        )

        return available_problem_ids_by_type


    async def _load_answer_steps(
        self,
        session: "AsyncSession",
        entrance_test_session_id: uuid.UUID,
    ) -> list[tuple[uuid.UUID, Outcome, float]]:
        result = await session.execute(
            select(
                Problem.problem_type_id,
                Difficulty.coefficient,
                ProblemAnswerOption.type,
            )
            .select_from(ResponseEvent)
            .join(Problem, Problem.id == ResponseEvent.problem_id)
            .join(Difficulty, Difficulty.id == Problem.difficulty_id)
            .join(ProblemAnswerOption, ProblemAnswerOption.id == ResponseEvent.answer_option_id)
            .where(ResponseEvent.entrance_test_session_id == entrance_test_session_id)
            .order_by(ResponseEvent.created_at, ResponseEvent.id)
        )

        answer_steps = [
            (
                problem_type_id,
                _map_answer_option_type_to_outcome(answer_option_type),
                float(difficulty_weight),
            )
            for problem_type_id, difficulty_weight, answer_option_type in result.all()
        ]

        logger.debug(
            "Loaded entrance assessment answer steps for session {}: steps={}",
            entrance_test_session_id,
            len(answer_steps),
        )

        return answer_steps


    def _resolve_available_problem_type_indices(
        self,
        graph_artifact: GraphArtifact,
        available_problem_ids_by_type: dict[uuid.UUID, list[uuid.UUID]],
    ) -> set[int]:
        return {
            graph_artifact.index_by_id[problem_type_id]
            for problem_type_id in available_problem_ids_by_type
            if problem_type_id in graph_artifact.index_by_id
        }


def _map_answer_option_type_to_outcome(
    answer_option_type: ProblemAnswerOptionType,
) -> Outcome:
    if answer_option_type == ProblemAnswerOptionType.RIGHT:
        return Outcome.CORRECT
    if answer_option_type == ProblemAnswerOptionType.I_DONT_KNOW:
        return Outcome.I_DONT_KNOW
    return Outcome.INCORRECT
