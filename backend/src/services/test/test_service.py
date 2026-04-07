from __future__ import annotations

from datetime import UTC, datetime
import uuid
from typing import TYPE_CHECKING, Any, Literal, TypedDict, cast

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from src.config import get_app_config
from src.core.logging import get_logger
from src.math_models.graph_assessment import (
    ExactInferenceStructureError,
    Outcome,
    ResponseModel,
    apply_answer_step,
    build_exact_inference_artifact,
    build_final_result,
    build_graph_artifact,
    restore_runtime,
    select_next_node,
    should_stop,
)
from src.models.alchemy import (
    Course,
    CourseEnrollment,
    CourseGraphVersion,
    CourseGraphVersionNode,
    GraphAssessment,
    Problem,
    ProblemAnswerOption,
    ProblemType,
    ResponseEvent,
    TestAttempt,
)
from src.models.pydantic.graph_assessment import GraphAssessmentResponse
from src.models.pydantic.response import ResponseCreate
from src.models.pydantic.test import (
    CourseTestAttemptHistoryItemResponse,
    CourseTestHistoryResponse,
    ProblemSolutionResponse,
    TestAnswerRequest,
    TestAnswerResponse,
    TestAttemptReviewResponse,
    TestAttemptResponse,
    TestCurrentProblemResponse,
    TestRevealSolutionResponse,
    TestReviewResponseItem,
    TestStartRequest,
)
from src.services.graph_assessment import (
    GraphAssessmentReviewService,
    ReviewCourseNodeContext,
)
from src.services.graph_assessment.graph_assessment_service import build_graph_assessment_response
from src.services.problem.loader import load_problem_or_404
from src.services.problem.mapper import build_problem_response
from src.services.response import ResponseRecorderService
from src.services.catalog.difficulty_service import build_difficulty_response
from src.storage.db.enums import (
    CourseGraphVersionStatus,
    GraphAssessmentReviewStatus,
    ProblemAnswerOptionType,
    TestAttemptKind,
    TestAttemptStatus,
)
from src.storage.storage_manager import StorageManager

__test__ = False

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.models.alchemy import CourseNode
    from src.models.pydantic.assessment_runtime import (
        ExactInferenceArtifact,
        FinalResult,
        GraphArtifact,
        RuntimeSnapshot,
    )


RuntimeKind = Literal["dag_frontier_v1", "exact_forest_bayes_v2"]

DAG_FRONTIER_RUNTIME_KIND: RuntimeKind = "dag_frontier_v1"
EXACT_FOREST_RUNTIME_KIND: RuntimeKind = "exact_forest_bayes_v2"

logger = get_logger(__name__)


class TestRuntimeState(TypedDict):
    runtime_kind: RuntimeKind
    asked_course_node_ids: list[str]
    learned_course_node_ids: list[str]
    failed_course_node_ids: list[str]
    target_course_node_ids: list[str]
    current_course_node_id: str | None
    assessment_node_score_by_course_node_id: dict[str, float]


class NextProblemSelection(TypedDict):
    problem: Problem | None
    course_node_id: uuid.UUID | None
    ready_without_problem_ids: list[uuid.UUID]


class GraphStatePayload(TypedDict):
    learned_course_node_ids: list[str]
    ready_course_node_ids: list[str]
    locked_course_node_ids: list[str]
    failed_course_node_ids: list[str]
    answered_course_node_ids: list[str]


class TestService:
    __test__ = False

    def __init__(self, storage_manager: StorageManager) -> None:
        self.storage_manager = storage_manager
        self.response_recorder_service = ResponseRecorderService()
        self.review_service = GraphAssessmentReviewService()


    async def start_test(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        data: TestStartRequest,
    ) -> TestCurrentProblemResponse:
        async with self.storage_manager.session_ctx() as session:
            course = await self._load_course_or_404(session, course_id)
            await self._ensure_active_enrollment(session, user_id, course_id)
            await self._ensure_no_active_test_attempt(session, user_id)
            await self._ensure_no_open_course_test_attempt(session, user_id, course_id)
            graph_version = await self._load_published_graph_version_or_409(session, course)
            target_course_node_ids = await self._resolve_target_course_node_ids(
                session=session,
                user_id=user_id,
                course_id=course_id,
                graph_version=graph_version,
                kind=data.kind,
                requested_target_course_node_ids=data.target_course_node_ids,
            )

            if data.kind == TestAttemptKind.ENTRANCE:
                has_active_assessment = await self._has_active_course_assessment(
                    session,
                    user_id,
                    course_id,
                )
                if has_active_assessment:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Entrance test is available only when there is no active assessment",
                    )

            test_attempt = TestAttempt(
                user_id=user_id,
                graph_version_id=graph_version.id,
                kind=data.kind,
                status=TestAttemptStatus.ACTIVE,
                current_problem_id=None,
                config_snapshot=self._build_test_config_snapshot(
                    graph_version=graph_version,
                    target_course_node_ids=target_course_node_ids,
                    requested_target_course_node_ids=data.target_course_node_ids,
                ),
                metadata_json=self._build_runtime_state_payload(
                    self._build_empty_runtime_state(
                        graph_version=graph_version,
                        target_course_node_ids=target_course_node_ids,
                    )
                ),
                started_at=datetime.now(UTC),
                paused_at=None,
                total_paused_seconds=0,
                ended_at=None,
            )
            session.add(test_attempt)
            await session.flush()

            graph_version = await self._load_graph_version_or_404(
                session,
                test_attempt.graph_version_id,
            )
            next_problem = await self._assign_next_problem(session, test_attempt, graph_version)
            await session.flush()
            await session.refresh(test_attempt)

            logger.info(
                "Started test attempt: test_attempt_id={}, user_id={}, course_id={}, graph_version_id={}, kind={}, target_node_count={}, current_problem_id={}",
                test_attempt.id,
                user_id,
                course_id,
                graph_version.id,
                data.kind,
                len(target_course_node_ids),
                test_attempt.current_problem_id,
            )
            return TestCurrentProblemResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                problem=build_problem_response(next_problem) if next_problem is not None else None,
            )


    async def get_current_test(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> TestCurrentProblemResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_open_course_test_attempt_or_404(
                session,
                user_id,
                course_id,
            )
            current_problem = await self._load_optional_current_problem(session, test_attempt)
            return TestCurrentProblemResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                problem=build_problem_response(current_problem) if current_problem is not None else None,
            )


    async def pause_test(self, user_id: uuid.UUID, test_attempt_id: uuid.UUID) -> TestAttemptResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_test_attempt_or_404(session, user_id, test_attempt_id)
            if test_attempt.status != TestAttemptStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only active test attempts can be paused",
                )

            paused_at = datetime.now(UTC)
            test_attempt.status = TestAttemptStatus.PAUSED
            test_attempt.paused_at = paused_at
            await session.flush()
            await session.refresh(test_attempt)
            logger.info(
                "Paused test attempt: test_attempt_id={}, user_id={}, paused_at={}",
                test_attempt_id,
                user_id,
                paused_at.isoformat(),
            )
            return TestAttemptResponse.model_validate(test_attempt)


    async def resume_test(
        self,
        user_id: uuid.UUID,
        test_attempt_id: uuid.UUID,
    ) -> TestCurrentProblemResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_test_attempt_or_404(session, user_id, test_attempt_id)
            if test_attempt.status != TestAttemptStatus.PAUSED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only paused test attempts can be resumed",
                )

            await self._ensure_no_active_test_attempt(session, user_id)
            test_attempt.status = TestAttemptStatus.ACTIVE
            resumed_at = datetime.now(UTC)
            if test_attempt.paused_at is not None:
                paused_seconds = int((resumed_at - test_attempt.paused_at).total_seconds())
                test_attempt.total_paused_seconds = max(
                    0,
                    test_attempt.total_paused_seconds + max(0, paused_seconds),
                )
            test_attempt.paused_at = None
            graph_version = await self._load_graph_version_or_404(session, test_attempt.graph_version_id)
            current_problem = await self._load_optional_current_problem(session, test_attempt)
            if current_problem is None:
                current_problem = await self._assign_next_problem(session, test_attempt, graph_version)
            await session.flush()
            await session.refresh(test_attempt)

            logger.info(
                "Resumed test attempt: test_attempt_id={}, user_id={}, current_problem_id={}, total_paused_seconds={}",
                test_attempt_id,
                user_id,
                test_attempt.current_problem_id,
                test_attempt.total_paused_seconds,
            )
            return TestCurrentProblemResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                problem=build_problem_response(current_problem) if current_problem is not None else None,
            )


    async def submit_answer(
        self,
        user_id: uuid.UUID,
        test_attempt_id: uuid.UUID,
        data: TestAnswerRequest,
    ) -> TestAnswerResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_test_attempt_or_404(session, user_id, test_attempt_id)
            if test_attempt.status != TestAttemptStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test attempt is not active",
                )
            if test_attempt.current_problem_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test attempt does not have a current problem",
                )
            if test_attempt.current_problem_id != data.problem_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Submitted problem does not match the current test problem",
                )

            graph_version = await self._load_graph_version_or_404(session, test_attempt.graph_version_id)
            problem = await load_problem_or_404(session, data.problem_id)
            answer_option = self._find_answer_option(problem, data.answer_option_id)
            runtime_state = self._read_runtime_state(test_attempt.metadata_json)
            current_course_node_id = runtime_state["current_course_node_id"]
            if current_course_node_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Current course node is not stored for this test attempt",
                )

            current_course_node_uuid = uuid.UUID(current_course_node_id)
            difficulty_response = build_difficulty_response(problem.difficulty)
            recorded_response = await self.response_recorder_service.record_response(
                session=session,
                user_id=user_id,
                data=ResponseCreate(
                    problem_id=problem.id,
                    answer_option_id=answer_option.id,
                    test_attempt_id=test_attempt.id,
                    problem_type_id=problem.problem_type_id,
                    course_node_id=current_course_node_uuid,
                    answer_option_type=answer_option.type,
                    difficulty=problem.difficulty,
                    difficulty_weight=difficulty_response.coefficient,
                ),
            )
            should_complete = self._apply_answer_to_runtime_state(
                test_attempt=test_attempt,
                graph_version=graph_version,
                runtime_state=runtime_state,
                course_node_id=current_course_node_uuid,
                answer_option_type=answer_option.type,
                difficulty_weight=difficulty_response.coefficient,
            )
            test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)

            next_problem: Problem | None = None
            graph_assessment_response: GraphAssessmentResponse | None = None
            if should_complete:
                graph_assessment = await self._complete_test_attempt(
                    session,
                    test_attempt,
                    graph_version,
                    runtime_state,
                )
                graph_assessment_response = (
                    build_graph_assessment_response(graph_assessment)
                    if graph_assessment is not None
                    else None
                )
            else:
                next_problem = await self._assign_next_problem(session, test_attempt, graph_version)
                if next_problem is None:
                    graph_assessment = await self._complete_test_attempt(
                        session,
                        test_attempt,
                        graph_version,
                        runtime_state,
                    )
                    graph_assessment_response = (
                        build_graph_assessment_response(graph_assessment)
                        if graph_assessment is not None
                        else None
                    )

            await session.flush()
            await session.refresh(test_attempt)
            logger.info(
                "Stored test answer: test_attempt_id={}, user_id={}, course_node_id={}, answer_option_type={}, next_problem_id={}, status={}, runtime_kind={}, completed={}",
                test_attempt_id,
                user_id,
                current_course_node_uuid,
                answer_option.type,
                test_attempt.current_problem_id,
                test_attempt.status,
                runtime_state["runtime_kind"],
                graph_assessment_response is not None,
            )
            return TestAnswerResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                response=recorded_response,
                next_problem=build_problem_response(next_problem) if next_problem is not None else None,
                graph_assessment=graph_assessment_response,
            )


    async def reveal_solution(
        self,
        user_id: uuid.UUID,
        test_attempt_id: uuid.UUID,
    ) -> TestRevealSolutionResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_test_attempt_or_404(session, user_id, test_attempt_id)
            if test_attempt.status != TestAttemptStatus.ACTIVE:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test attempt is not active",
                )
            if test_attempt.current_problem_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Test attempt does not have a current problem",
                )

            graph_version = await self._load_graph_version_or_404(session, test_attempt.graph_version_id)
            problem = await load_problem_or_404(session, test_attempt.current_problem_id)
            answer_option = self._pick_reveal_answer_option(problem)
            runtime_state = self._read_runtime_state(test_attempt.metadata_json)
            current_course_node_id = runtime_state["current_course_node_id"]
            if current_course_node_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Current course node is not stored for this test attempt",
                )

            current_course_node_uuid = uuid.UUID(current_course_node_id)
            difficulty_response = build_difficulty_response(problem.difficulty)
            recorded_response = await self.response_recorder_service.record_response(
                session=session,
                user_id=user_id,
                data=ResponseCreate(
                    problem_id=problem.id,
                    answer_option_id=answer_option.id,
                    test_attempt_id=test_attempt.id,
                    problem_type_id=problem.problem_type_id,
                    course_node_id=current_course_node_uuid,
                    answer_option_type=answer_option.type,
                    difficulty=problem.difficulty,
                    difficulty_weight=difficulty_response.coefficient,
                    revealed_solution=True,
                ),
            )
            should_complete = self._apply_answer_to_runtime_state(
                test_attempt=test_attempt,
                graph_version=graph_version,
                runtime_state=runtime_state,
                course_node_id=current_course_node_uuid,
                answer_option_type=answer_option.type,
                difficulty_weight=difficulty_response.coefficient,
            )
            test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)

            next_problem: Problem | None = None
            graph_assessment_response: GraphAssessmentResponse | None = None
            if should_complete:
                graph_assessment = await self._complete_test_attempt(
                    session,
                    test_attempt,
                    graph_version,
                    runtime_state,
                )
                graph_assessment_response = (
                    build_graph_assessment_response(graph_assessment)
                    if graph_assessment is not None
                    else None
                )
            else:
                next_problem = await self._assign_next_problem(session, test_attempt, graph_version)
                if next_problem is None:
                    graph_assessment = await self._complete_test_attempt(
                        session,
                        test_attempt,
                        graph_version,
                        runtime_state,
                    )
                    graph_assessment_response = (
                        build_graph_assessment_response(graph_assessment)
                        if graph_assessment is not None
                        else None
                    )

            await session.flush()
            await session.refresh(test_attempt)
            logger.info(
                "Revealed solution in test attempt",
                test_attempt_id=str(test_attempt_id),
                user_id=str(user_id),
                problem_id=str(problem.id),
                course_node_id=str(current_course_node_uuid),
                next_problem_id=(
                    str(test_attempt.current_problem_id)
                    if test_attempt.current_problem_id is not None
                    else None
                ),
            )
            return TestRevealSolutionResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                response=recorded_response,
                revealed_solution=ProblemSolutionResponse(
                    problem_id=problem.id,
                    solution=problem.solution,
                    solution_images=problem.solution_images,
                ),
                next_problem=build_problem_response(next_problem) if next_problem is not None else None,
                graph_assessment=graph_assessment_response,
            )


    async def get_attempt_review(
        self,
        user_id: uuid.UUID,
        test_attempt_id: uuid.UUID,
    ) -> TestAttemptReviewResponse:
        async with self.storage_manager.session_ctx() as session:
            test_attempt = await self._load_test_attempt_or_404(session, user_id, test_attempt_id)
            result = await session.execute(
                select(ResponseEvent)
                .options(
                    selectinload(ResponseEvent.problem).selectinload(Problem.subtopic),
                    selectinload(ResponseEvent.problem)
                    .selectinload(Problem.problem_type)
                    .selectinload(ProblemType.prerequisite_links),
                    selectinload(ResponseEvent.problem).selectinload(Problem.course_node),
                    selectinload(ResponseEvent.problem).selectinload(Problem.answer_options),
                )
                .where(ResponseEvent.test_attempt_id == test_attempt.id)
                .order_by(ResponseEvent.created_at.asc(), ResponseEvent.id.asc())
            )
            response_events = list(result.scalars().unique().all())
            review_items = [
                TestReviewResponseItem(
                    response_id=response_event.id,
                    problem=build_problem_response(response_event.problem),
                    chosen_answer_option_id=response_event.answer_option_id,
                    chosen_answer_option_type=(
                        response_event.answer_option_type
                        if response_event.answer_option_type is not None
                        else ProblemAnswerOptionType.WRONG
                    ),
                    revealed_solution=response_event.revealed_solution,
                    solution=response_event.problem.solution,
                    solution_images=response_event.problem.solution_images,
                    created_at=response_event.created_at,
                )
                for response_event in response_events
            ]
            return TestAttemptReviewResponse(
                test_attempt=TestAttemptResponse.model_validate(test_attempt),
                items=review_items,
            )


    async def list_course_attempt_history(
        self,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> CourseTestHistoryResponse:
        async with self.storage_manager.session_ctx() as session:
            result = await session.execute(
                select(TestAttempt)
                .join(
                    CourseGraphVersion,
                    CourseGraphVersion.id == TestAttempt.graph_version_id,
                )
                .where(
                    TestAttempt.user_id == user_id,
                    CourseGraphVersion.course_id == course_id,
                )
                .order_by(TestAttempt.created_at.desc(), TestAttempt.id.desc())
            )
            attempts = list(result.scalars().all())
            return CourseTestHistoryResponse(
                attempts=[
                    CourseTestAttemptHistoryItemResponse(
                        id=attempt.id,
                        graph_version_id=attempt.graph_version_id,
                        kind=attempt.kind,
                        status=attempt.status,
                        started_at=attempt.started_at,
                        ended_at=attempt.ended_at,
                        created_at=attempt.created_at,
                        updated_at=attempt.updated_at,
                    )
                    for attempt in attempts
                ]
            )


    async def reset_course(self, user_id: uuid.UUID, course_id: uuid.UUID) -> None:
        async with self.storage_manager.session_ctx() as session:
            await self._load_course_or_404(session, course_id)
            await self._deactivate_course_assessments(session, user_id, course_id)
            await self._cancel_open_course_tests(session, user_id, course_id)
            logger.info(
                "Reset course for user: user_id={}, course_id={}",
                user_id,
                course_id,
            )


    async def _assign_next_problem(
        self,
        session: AsyncSession,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
    ) -> Problem | None:
        runtime_state = self._read_runtime_state(test_attempt.metadata_json)
        next_problem_selection = await self._select_next_problem(session, test_attempt, graph_version, runtime_state)
        if next_problem_selection["problem"] is None:
            test_attempt.current_problem_id = None
            runtime_state["current_course_node_id"] = None
            test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)
            if next_problem_selection["ready_without_problem_ids"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Ready course nodes do not have available problems",
                )
            return None

        selected_problem = next_problem_selection["problem"]
        selected_course_node_id = next_problem_selection["course_node_id"]
        test_attempt.current_problem_id = selected_problem.id
        runtime_state["current_course_node_id"] = (
            str(selected_course_node_id)
            if selected_course_node_id is not None
            else None
        )
        test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)
        return selected_problem


    async def _select_next_problem(
        self,
        session: AsyncSession,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
    ) -> NextProblemSelection:
        target_course_node_ids = self._read_target_course_node_ids(
            test_attempt=test_attempt,
            graph_version=graph_version,
        )
        if runtime_state["runtime_kind"] == EXACT_FOREST_RUNTIME_KIND:
            return await self._select_next_problem_with_exact_runtime(
                session=session,
                test_attempt=test_attempt,
                graph_version=graph_version,
                runtime_state=runtime_state,
                target_course_node_ids=target_course_node_ids,
            )

        state = self._build_graph_state(graph_version, runtime_state)
        ready_without_problem_ids: list[uuid.UUID] = []
        for ready_course_node_id_str in state["ready_course_node_ids"]:
            ready_course_node_id = uuid.UUID(ready_course_node_id_str)
            if ready_course_node_id not in target_course_node_ids:
                continue
            ready_course_node = self._find_course_node(graph_version, ready_course_node_id)
            selected_problem = await self._pick_problem_for_course_node(
                session,
                test_attempt.id,
                ready_course_node,
            )
            if selected_problem is not None:
                return {
                    "problem": selected_problem,
                    "course_node_id": ready_course_node_id,
                    "ready_without_problem_ids": ready_without_problem_ids,
                }
            ready_without_problem_ids.append(ready_course_node_id)

        return {
            "problem": None,
            "course_node_id": None,
            "ready_without_problem_ids": ready_without_problem_ids,
        }


    async def _select_next_problem_with_exact_runtime(
        self,
        session: AsyncSession,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
        target_course_node_ids: set[uuid.UUID],
    ) -> NextProblemSelection:
        graph_artifact, _, runtime_snapshot = (
            self._build_exact_runtime_context(
                graph_version=graph_version,
                config_snapshot=test_attempt.config_snapshot,
                runtime_state=runtime_state,
            )
        )
        available_node_ids = set(target_course_node_ids)
        blocked_node_ids: list[uuid.UUID] = []
        assessment_config = self._get_assessment_config(test_attempt.config_snapshot)

        while available_node_ids:
            selection = select_next_node(
                graph_artifact=graph_artifact,
                runtime=runtime_snapshot,
                available_node_ids=available_node_ids,
                learned_mastery_probability=self._get_projected_learned_mastery_probability(
                    assessment_config
                ),
                unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                    assessment_config
                ),
            )
            should_stop_result, stop_reason = should_stop(
                graph_artifact=graph_artifact,
                runtime=runtime_snapshot,
                selection=selection,
                entropy_stop=float(assessment_config["entropy_stop"]),
                utility_stop=float(assessment_config["utility_stop"]),
                leader_probability_stop=self._coerce_optional_float(
                    assessment_config.get("leader_probability_stop")
                ),
                max_questions=int(assessment_config["max_questions"]),
                learned_mastery_probability=self._get_projected_learned_mastery_probability(
                    assessment_config
                ),
                unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                    assessment_config
                ),
                projection_confidence_stop=self._get_projection_confidence_stop(
                    assessment_config
                ),
                frontier_confidence_stop=self._get_frontier_confidence_stop(
                    assessment_config
                ),
            )
            logger.info(
                "Selected exact-runtime next node candidate: test_attempt_id={}, stop={}, stop_reason={}, node_id={}, utility={}, available_nodes={}",
                test_attempt.id,
                should_stop_result,
                stop_reason,
                selection.node_id,
                selection.max_utility,
                len(available_node_ids),
            )
            if should_stop_result:
                return {
                    "problem": None,
                    "course_node_id": None,
                    "ready_without_problem_ids": [],
                }

            if selection.node_id is None:
                return {
                    "problem": None,
                    "course_node_id": None,
                    "ready_without_problem_ids": blocked_node_ids,
                }
            if selection.node_id not in available_node_ids:
                return {
                    "problem": None,
                    "course_node_id": None,
                    "ready_without_problem_ids": blocked_node_ids,
                }

            course_node = self._find_course_node(graph_version, selection.node_id)
            selected_problem = await self._pick_problem_for_course_node(
                session,
                test_attempt.id,
                course_node,
            )
            if selected_problem is not None:
                return {
                    "problem": selected_problem,
                    "course_node_id": selection.node_id,
                    "ready_without_problem_ids": blocked_node_ids,
                }

            available_node_ids.discard(selection.node_id)
            blocked_node_ids.append(selection.node_id)

        return {
            "problem": None,
            "course_node_id": None,
            "ready_without_problem_ids": blocked_node_ids,
        }


    async def _pick_problem_for_course_node(
        self,
        session: AsyncSession,
        test_attempt_id: uuid.UUID,
        course_node: CourseNode,
    ) -> Problem | None:
        used_problem_ids = await self._load_used_problem_ids(session, test_attempt_id)
        result = await session.execute(
            select(Problem)
            .options(
                selectinload(Problem.subtopic),
                selectinload(Problem.problem_type).selectinload(ProblemType.prerequisite_links),
                selectinload(Problem.course_node),
                selectinload(Problem.answer_options),
            )
            .where(Problem.course_node_id == course_node.id)
            .order_by(Problem.condition, Problem.id)
        )
        direct_problems = list(result.scalars().unique().all())
        selected_problem = self._pick_unused_problem(direct_problems, used_problem_ids)
        if selected_problem is not None:
            return selected_problem

        if course_node.problem_type_id is None:
            return None

        result = await session.execute(
            select(Problem)
            .options(
                selectinload(Problem.subtopic),
                selectinload(Problem.problem_type).selectinload(ProblemType.prerequisite_links),
                selectinload(Problem.course_node),
                selectinload(Problem.answer_options),
            )
            .where(Problem.problem_type_id == course_node.problem_type_id)
            .order_by(Problem.condition, Problem.id)
        )
        fallback_problems = list(result.scalars().unique().all())
        return self._pick_unused_problem(fallback_problems, used_problem_ids)


    async def _load_used_problem_ids(
        self,
        session: AsyncSession,
        test_attempt_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        result = await session.execute(
            select(ResponseEvent.problem_id).where(ResponseEvent.test_attempt_id == test_attempt_id)
        )
        return set(result.scalars().all())


    def _pick_unused_problem(
        self,
        problems: list[Problem],
        used_problem_ids: set[uuid.UUID],
    ) -> Problem | None:
        if not problems:
            return None
        return next(
            (
                problem
                for problem in problems
                if problem.id not in used_problem_ids
            ),
            None,
        )


    async def _complete_test_attempt(
        self,
        session: AsyncSession,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
    ) -> GraphAssessment | None:
        ended_at = datetime.now(UTC)
        if test_attempt.paused_at is not None:
            paused_seconds = int((ended_at - test_attempt.paused_at).total_seconds())
            test_attempt.total_paused_seconds = max(
                0,
                test_attempt.total_paused_seconds + max(0, paused_seconds),
            )

        test_attempt.status = TestAttemptStatus.COMPLETED
        test_attempt.current_problem_id = None
        test_attempt.ended_at = ended_at
        test_attempt.paused_at = None
        runtime_state["current_course_node_id"] = None
        test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)

        if not self._is_mastery_changing_kind(test_attempt.kind):
            return None

        state, state_confidence, metadata_json = self._build_assessment_result_payload(
            test_attempt=test_attempt,
            graph_version=graph_version,
            runtime_state=runtime_state,
        )
        if await self._is_perfect_attempt(session=session, test_attempt_id=test_attempt.id):
            state_confidence = 1.0
            logger.info(
                "Applied perfect-attempt confidence override",
                test_attempt_id=str(test_attempt.id),
                confidence=state_confidence,
            )
        course_id = graph_version.course_id
        await self._deactivate_course_assessments(session, test_attempt.user_id, course_id)

        graph_assessment = GraphAssessment(
            user_id=test_attempt.user_id,
            graph_version_id=test_attempt.graph_version_id,
            source_test_attempt_id=test_attempt.id,
            state=state,
            state_confidence=state_confidence,
            is_active=True,
            assessment_kind=test_attempt.kind,
            metadata_json=metadata_json,
            measured_at=datetime.now(UTC),
        )
        session.add(graph_assessment)
        await session.flush()
        await self._populate_assessment_review(
            graph_assessment=graph_assessment,
            graph_version=graph_version,
        )
        await session.flush()
        await session.refresh(graph_assessment)
        return graph_assessment


    async def _populate_assessment_review(
        self,
        graph_assessment: GraphAssessment,
        graph_version: CourseGraphVersion,
    ) -> None:
        state_counts = self._build_state_counts(graph_assessment.state)
        course_title = graph_version.course.title if graph_version.course is not None else "Course"
        course_description = graph_version.course.description if graph_version.course is not None else None
        node_contexts = self._build_review_node_contexts(
            graph_version=graph_version,
            graph_state=graph_assessment.state,
            metadata_json=graph_assessment.metadata_json,
        )
        generated_review = await self.review_service.generate_review(
            course_title=course_title,
            course_description=course_description,
            node_contexts=node_contexts,
            assessment_kind=graph_assessment.assessment_kind,
            state_confidence=graph_assessment.state_confidence,
            learned_count=state_counts["learned"],
            ready_count=state_counts["ready"],
            locked_count=state_counts["locked"],
            failed_count=state_counts["failed"],
        )
        graph_assessment.review_model = generated_review.review_model
        graph_assessment.review_status = generated_review.status
        if generated_review.status == GraphAssessmentReviewStatus.SUCCEEDED:
            graph_assessment.review_text = generated_review.review_text
            graph_assessment.review_recommendations = generated_review.review_recommendations
            graph_assessment.review_error = None
            graph_assessment.review_generated_at = generated_review.generated_at
            return

        graph_assessment.review_text = None
        graph_assessment.review_recommendations = self._build_deterministic_recommendations(state_counts)
        graph_assessment.review_error = generated_review.review_error
        graph_assessment.review_generated_at = None


    async def _deactivate_course_assessments(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(GraphAssessment)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == GraphAssessment.graph_version_id,
            )
            .where(
                GraphAssessment.user_id == user_id,
                GraphAssessment.is_active.is_(True),
                CourseGraphVersion.course_id == course_id,
            )
        )
        for graph_assessment in result.scalars().all():
            graph_assessment.is_active = False


    async def _cancel_open_course_tests(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(TestAttempt)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                TestAttempt.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                TestAttempt.status.in_(
                    [
                        TestAttemptStatus.ACTIVE,
                        TestAttemptStatus.PAUSED,
                    ]
                ),
            )
        )
        for test_attempt in result.scalars().all():
            ended_at = datetime.now(UTC)
            if test_attempt.paused_at is not None:
                paused_seconds = int((ended_at - test_attempt.paused_at).total_seconds())
                test_attempt.total_paused_seconds = max(
                    0,
                    test_attempt.total_paused_seconds + max(0, paused_seconds),
                )
            test_attempt.status = TestAttemptStatus.CANCELLED
            test_attempt.current_problem_id = None
            test_attempt.ended_at = ended_at
            test_attempt.paused_at = None
            runtime_state = self._read_runtime_state(test_attempt.metadata_json)
            runtime_state["current_course_node_id"] = None
            test_attempt.metadata_json = self._build_runtime_state_payload(runtime_state)


    async def _resolve_target_course_node_ids(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        graph_version: CourseGraphVersion,
        kind: TestAttemptKind,
        requested_target_course_node_ids: list[uuid.UUID] | None,
    ) -> list[uuid.UUID]:
        allowed_course_node_ids = {
            version_node.course_node_id
            for version_node in graph_version.version_nodes
        }
        if requested_target_course_node_ids is not None and requested_target_course_node_ids:
            normalized_requested_ids = list(dict.fromkeys(requested_target_course_node_ids))
            unsupported_ids = [
                str(course_node_id)
                for course_node_id in normalized_requested_ids
                if course_node_id not in allowed_course_node_ids
            ]
            if unsupported_ids:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Target nodes are not part of the graph version: {', '.join(unsupported_ids)}",
                )
            return normalized_requested_ids

        if kind != TestAttemptKind.MISTAKES:
            return sorted(allowed_course_node_ids, key=str)

        recent_mistake_node_ids = await self._load_recent_mistake_course_node_ids(
            session=session,
            user_id=user_id,
            course_id=course_id,
            allowed_course_node_ids=allowed_course_node_ids,
        )
        if recent_mistake_node_ids:
            return recent_mistake_node_ids
        return sorted(allowed_course_node_ids, key=str)


    async def _load_recent_mistake_course_node_ids(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
        allowed_course_node_ids: set[uuid.UUID],
    ) -> list[uuid.UUID]:
        result = await session.execute(
            select(ResponseEvent.course_node_id)
            .join(
                TestAttempt,
                TestAttempt.id == ResponseEvent.test_attempt_id,
            )
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                ResponseEvent.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                ResponseEvent.course_node_id.is_not(None),
                or_(
                    ResponseEvent.answer_option_type != ProblemAnswerOptionType.RIGHT,
                    ResponseEvent.revealed_solution.is_(True),
                ),
            )
            .order_by(ResponseEvent.created_at.desc(), ResponseEvent.id.desc())
            .limit(64)
        )
        recent_ids: list[uuid.UUID] = []
        for raw_node_id in result.scalars().all():
            if raw_node_id is None:
                continue
            if raw_node_id not in allowed_course_node_ids:
                continue
            if raw_node_id in recent_ids:
                continue
            recent_ids.append(raw_node_id)
        return recent_ids


    def _read_target_course_node_ids(
        self,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
    ) -> set[uuid.UUID]:
        allowed_course_node_ids = {
            version_node.course_node_id
            for version_node in graph_version.version_nodes
        }
        raw_target_ids = test_attempt.config_snapshot.get("target_course_node_ids")
        if not isinstance(raw_target_ids, list):
            return allowed_course_node_ids

        parsed_target_ids: set[uuid.UUID] = set()
        for raw_target_id in raw_target_ids:
            try:
                parsed_target_id = uuid.UUID(str(raw_target_id))
            except ValueError:
                continue
            if parsed_target_id in allowed_course_node_ids:
                parsed_target_ids.add(parsed_target_id)

        if parsed_target_ids:
            return parsed_target_ids
        return allowed_course_node_ids


    @staticmethod
    def _is_mastery_changing_kind(kind: TestAttemptKind) -> bool:
        return kind in {TestAttemptKind.ENTRANCE, TestAttemptKind.GENERAL}


    async def _load_course_or_404(
        self,
        session: AsyncSession,
        course_id: uuid.UUID,
    ) -> Course:
        course = await session.get(Course, course_id)
        if course is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return course


    async def _load_published_graph_version_or_409(
        self,
        session: AsyncSession,
        course: Course,
    ) -> CourseGraphVersion:
        if course.current_graph_version_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Course does not have a published graph version",
            )
        graph_version = await self._load_graph_version_or_404(session, course.current_graph_version_id)
        if graph_version.status != CourseGraphVersionStatus.READY:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Published graph version is not ready",
            )
        return graph_version


    async def _load_graph_version_or_404(
        self,
        session: AsyncSession,
        graph_version_id: uuid.UUID,
    ) -> CourseGraphVersion:
        result = await session.execute(
            select(CourseGraphVersion)
            .options(
                selectinload(CourseGraphVersion.course),
                selectinload(CourseGraphVersion.version_nodes).selectinload(
                    CourseGraphVersionNode.course_node
                ),
                selectinload(CourseGraphVersion.edges),
            )
            .where(CourseGraphVersion.id == graph_version_id)
        )
        graph_version = result.scalar_one_or_none()
        if graph_version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course graph version not found",
            )
        return graph_version


    async def _ensure_active_enrollment(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(CourseEnrollment).where(
                CourseEnrollment.user_id == user_id,
                CourseEnrollment.course_id == course_id,
                CourseEnrollment.is_active.is_(True),
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is not actively enrolled in this course",
            )


    async def _ensure_no_active_test_attempt(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(TestAttempt.id).where(
                TestAttempt.user_id == user_id,
                TestAttempt.status == TestAttemptStatus.ACTIVE,
            )
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already has an active test attempt",
            )


    async def _ensure_no_open_course_test_attempt(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> None:
        result = await session.execute(
            select(TestAttempt.id)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                TestAttempt.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                TestAttempt.status.in_(
                    [
                        TestAttemptStatus.ACTIVE,
                        TestAttemptStatus.PAUSED,
                    ]
                ),
            )
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User already has an open test attempt for this course",
            )


    async def _load_open_course_test_attempt_or_404(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> TestAttempt:
        result = await session.execute(
            select(TestAttempt)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == TestAttempt.graph_version_id,
            )
            .where(
                TestAttempt.user_id == user_id,
                CourseGraphVersion.course_id == course_id,
                TestAttempt.status.in_(
                    [
                        TestAttemptStatus.ACTIVE,
                        TestAttemptStatus.PAUSED,
                    ]
                ),
            )
            .order_by(TestAttempt.created_at.desc(), TestAttempt.id.desc())
        )
        test_attempt = result.scalar_one_or_none()
        if test_attempt is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Open test attempt not found",
            )
        return test_attempt


    async def _load_test_attempt_or_404(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        test_attempt_id: uuid.UUID,
    ) -> TestAttempt:
        result = await session.execute(
            select(TestAttempt).where(
                TestAttempt.id == test_attempt_id,
                TestAttempt.user_id == user_id,
            )
        )
        test_attempt = result.scalar_one_or_none()
        if test_attempt is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test attempt not found",
            )
        return test_attempt


    async def _has_active_course_assessment(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        course_id: uuid.UUID,
    ) -> bool:
        result = await session.execute(
            select(GraphAssessment.id)
            .join(
                CourseGraphVersion,
                CourseGraphVersion.id == GraphAssessment.graph_version_id,
            )
            .where(
                GraphAssessment.user_id == user_id,
                GraphAssessment.is_active.is_(True),
                CourseGraphVersion.course_id == course_id,
            )
        )
        return result.scalar_one_or_none() is not None


    async def _load_optional_current_problem(
        self,
        session: AsyncSession,
        test_attempt: TestAttempt,
    ) -> Problem | None:
        if test_attempt.current_problem_id is None:
            return None
        return await load_problem_or_404(session, test_attempt.current_problem_id)


    def _find_answer_option(
        self,
        problem: Problem,
        answer_option_id: uuid.UUID,
    ) -> ProblemAnswerOption:
        answer_option = next(
            (
                problem_answer_option
                for problem_answer_option in problem.answer_options
                if problem_answer_option.id == answer_option_id
            ),
            None,
        )
        if answer_option is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Answer option not found",
            )
        return answer_option


    def _pick_reveal_answer_option(self, problem: Problem) -> ProblemAnswerOption:
        i_dont_know_option = next(
            (
                answer_option
                for answer_option in problem.answer_options
                if answer_option.type == ProblemAnswerOptionType.I_DONT_KNOW
            ),
            None,
        )
        if i_dont_know_option is not None:
            return i_dont_know_option

        wrong_option = next(
            (
                answer_option
                for answer_option in problem.answer_options
                if answer_option.type == ProblemAnswerOptionType.WRONG
            ),
            None,
        )
        if wrong_option is not None:
            return wrong_option

        if not problem.answer_options:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem does not have answer options",
            )
        return problem.answer_options[0]


    def _apply_answer_to_runtime_state(
        self,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
        course_node_id: uuid.UUID,
        answer_option_type: ProblemAnswerOptionType,
        difficulty_weight: float,
    ) -> bool:
        if runtime_state["runtime_kind"] == EXACT_FOREST_RUNTIME_KIND:
            return self._apply_answer_to_exact_runtime_state(
                test_attempt=test_attempt,
                graph_version=graph_version,
                runtime_state=runtime_state,
                course_node_id=course_node_id,
                answer_option_type=answer_option_type,
                difficulty_weight=difficulty_weight,
            )

        course_node_id_str = str(course_node_id)
        if course_node_id_str not in runtime_state["asked_course_node_ids"]:
            runtime_state["asked_course_node_ids"].append(course_node_id_str)

        if answer_option_type == ProblemAnswerOptionType.RIGHT:
            if course_node_id_str not in runtime_state["learned_course_node_ids"]:
                runtime_state["learned_course_node_ids"].append(course_node_id_str)
            runtime_state["failed_course_node_ids"] = [
                failed_course_node_id
                for failed_course_node_id in runtime_state["failed_course_node_ids"]
                if failed_course_node_id != course_node_id_str
            ]
            return False

        if course_node_id_str not in runtime_state["failed_course_node_ids"]:
            runtime_state["failed_course_node_ids"].append(course_node_id_str)
        runtime_state["learned_course_node_ids"] = [
            learned_course_node_id
            for learned_course_node_id in runtime_state["learned_course_node_ids"]
            if learned_course_node_id != course_node_id_str
        ]
        return False


    def _build_empty_runtime_state(
        self,
        graph_version: CourseGraphVersion,
        target_course_node_ids: list[uuid.UUID],
    ) -> TestRuntimeState:
        runtime_kind = self._select_runtime_kind(graph_version)
        return {
            "runtime_kind": runtime_kind,
            "asked_course_node_ids": [],
            "learned_course_node_ids": [],
            "failed_course_node_ids": [],
            "target_course_node_ids": [str(course_node_id) for course_node_id in target_course_node_ids],
            "current_course_node_id": None,
            "assessment_node_score_by_course_node_id": {},
        }


    def _read_runtime_state(self, metadata_json: dict[str, object]) -> TestRuntimeState:
        runtime_kind = metadata_json.get("runtime_kind")
        asked_course_node_ids = self._read_string_list(metadata_json, "asked_course_node_ids")
        learned_course_node_ids = self._read_string_list(metadata_json, "learned_course_node_ids")
        failed_course_node_ids = self._read_string_list(metadata_json, "failed_course_node_ids")
        target_course_node_ids = self._read_string_list(metadata_json, "target_course_node_ids")
        current_course_node_id = metadata_json.get("current_course_node_id")
        assessment_node_score_by_course_node_id = self._read_float_mapping(
            metadata_json,
            "assessment_node_score_by_course_node_id",
        )
        return {
            "runtime_kind": (
                cast("RuntimeKind", runtime_kind)
                if runtime_kind in {DAG_FRONTIER_RUNTIME_KIND, EXACT_FOREST_RUNTIME_KIND}
                else DAG_FRONTIER_RUNTIME_KIND
            ),
            "asked_course_node_ids": asked_course_node_ids,
            "learned_course_node_ids": learned_course_node_ids,
            "failed_course_node_ids": failed_course_node_ids,
            "target_course_node_ids": target_course_node_ids,
            "current_course_node_id": (
                str(current_course_node_id)
                if isinstance(current_course_node_id, str)
                else None
            ),
            "assessment_node_score_by_course_node_id": assessment_node_score_by_course_node_id,
        }


    def _build_runtime_state_payload(self, runtime_state: TestRuntimeState) -> dict[str, object]:
        return {
            "runtime_kind": runtime_state["runtime_kind"],
            "asked_course_node_ids": list(runtime_state["asked_course_node_ids"]),
            "learned_course_node_ids": list(runtime_state["learned_course_node_ids"]),
            "failed_course_node_ids": list(runtime_state["failed_course_node_ids"]),
            "target_course_node_ids": list(runtime_state["target_course_node_ids"]),
            "current_course_node_id": runtime_state["current_course_node_id"],
            "assessment_node_score_by_course_node_id": dict(
                runtime_state["assessment_node_score_by_course_node_id"]
            ),
        }


    def _read_string_list(self, payload: dict[str, object], key: str) -> list[str]:
        raw_value = payload.get(key)
        if not isinstance(raw_value, list):
            return []
        return [str(item) for item in raw_value]


    def _read_float_mapping(self, payload: dict[str, object], key: str) -> dict[str, float]:
        raw_value = payload.get(key)
        if not isinstance(raw_value, dict):
            return {}

        normalized_mapping: dict[str, float] = {}
        for raw_key, raw_item in raw_value.items():
            try:
                normalized_mapping[str(raw_key)] = float(raw_item)
            except (TypeError, ValueError):
                continue

        return normalized_mapping


    def _apply_answer_to_exact_runtime_state(
        self,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
        course_node_id: uuid.UUID,
        answer_option_type: ProblemAnswerOptionType,
        difficulty_weight: float,
    ) -> bool:
        graph_artifact, exact_inference_artifact, runtime_snapshot = (
            self._build_exact_runtime_context(
                graph_version=graph_version,
                config_snapshot=test_attempt.config_snapshot,
                runtime_state=runtime_state,
            )
        )
        assessment_config = self._get_assessment_config(test_attempt.config_snapshot)
        outcome = self._map_answer_option_type_to_outcome(answer_option_type)
        step_result = apply_answer_step(
            graph_artifact=graph_artifact,
            exact_inference_artifact=exact_inference_artifact,
            runtime=runtime_snapshot,
            answered_node_id=course_node_id,
            outcome=outcome,
            instance_difficulty_weight=difficulty_weight,
            response_model=self._build_response_model(assessment_config),
            i_dont_know_scalar=float(assessment_config["i_dont_know_scalar"]),
            temperature_sharpening=float(assessment_config["temperature_sharpening"]),
            entropy_stop=float(assessment_config["entropy_stop"]),
            utility_stop=float(assessment_config["utility_stop"]),
            leader_probability_stop=self._coerce_optional_float(
                assessment_config.get("leader_probability_stop")
            ),
            max_questions=int(assessment_config["max_questions"]),
            available_node_ids=set(graph_artifact.node_ids),
            learned_mastery_probability=self._get_projected_learned_mastery_probability(
                assessment_config
            ),
            unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                assessment_config
            ),
            projection_confidence_stop=self._get_projection_confidence_stop(
                assessment_config
            ),
            frontier_confidence_stop=self._get_frontier_confidence_stop(
                assessment_config
            ),
        )
        runtime_state["asked_course_node_ids"] = [
            str(graph_artifact.node_ids[node_index])
            for node_index in step_result.runtime.asked_node_indices
        ]
        runtime_state["assessment_node_score_by_course_node_id"] = (
            self._build_node_score_by_course_node_id(
                graph_artifact=graph_artifact,
                runtime_snapshot=step_result.runtime,
            )
        )
        runtime_state["learned_course_node_ids"] = []
        runtime_state["failed_course_node_ids"] = []
        logger.info(
            "Applied exact-runtime answer update: test_attempt_id={}, course_node_id={}, outcome={}, should_stop={}, stop_reason={}, leader_state_probability={}",
            test_attempt.id,
            course_node_id,
            outcome,
            step_result.should_stop,
            step_result.stop_reason,
            step_result.runtime.leader_state_probability,
        )
        return step_result.should_stop


    def _build_test_config_snapshot(
        self,
        graph_version: CourseGraphVersion,
        target_course_node_ids: list[uuid.UUID],
        requested_target_course_node_ids: list[uuid.UUID] | None,
    ) -> dict[str, object]:
        runtime_kind = self._select_runtime_kind(graph_version)
        return {
            "selection_strategy": runtime_kind,
            "assessment": get_app_config().entrance_assessment_snapshot(),
            "target_course_node_ids": [str(course_node_id) for course_node_id in target_course_node_ids],
            "requested_target_course_node_ids": (
                [str(course_node_id) for course_node_id in requested_target_course_node_ids]
                if requested_target_course_node_ids is not None
                else []
            ),
        }


    def _select_runtime_kind(self, graph_version: CourseGraphVersion) -> RuntimeKind:
        try:
            graph_artifact = self._build_assessment_graph_artifact(graph_version)
            build_exact_inference_artifact(graph_artifact)
        except ExactInferenceStructureError:
            logger.info(
                "Graph version requires DAG fallback runtime: graph_version_id={}",
                graph_version.id,
            )
            return DAG_FRONTIER_RUNTIME_KIND

        logger.info(
            "Graph version supports exact inference runtime: graph_version_id={}",
            graph_version.id,
        )
        return EXACT_FOREST_RUNTIME_KIND


    def _build_assessment_graph_artifact(
        self,
        graph_version: CourseGraphVersion,
    ) -> GraphArtifact:
        ordered_node_ids = tuple(self._build_ordered_course_node_ids(graph_version))
        prerequisite_edges = tuple(
            sorted(
                (
                    (
                        edge.dependent_course_node_id,
                        edge.prerequisite_course_node_id,
                    )
                    for edge in graph_version.edges
                ),
                key=lambda edge: (str(edge[0]), str(edge[1])),
            )
        )
        return build_graph_artifact(
            node_ids=ordered_node_ids,
            prerequisite_edges=prerequisite_edges,
        )


    def _build_exact_runtime_context(
        self,
        graph_version: CourseGraphVersion,
        config_snapshot: dict[str, object],
        runtime_state: TestRuntimeState,
    ) -> tuple[GraphArtifact, ExactInferenceArtifact, RuntimeSnapshot]:
        graph_artifact = self._build_assessment_graph_artifact(graph_version)
        exact_inference_artifact = build_exact_inference_artifact(graph_artifact)
        runtime_snapshot = restore_runtime(
            graph_artifact=graph_artifact,
            exact_inference_artifact=exact_inference_artifact,
            node_score_by_id={
                uuid.UUID(course_node_id): node_score
                for course_node_id, node_score in runtime_state[
                    "assessment_node_score_by_course_node_id"
                ].items()
            },
            asked_node_ids=tuple(
                uuid.UUID(course_node_id)
                for course_node_id in runtime_state["asked_course_node_ids"]
            ),
            temperature_sharpening=float(
                self._get_assessment_config(config_snapshot)["temperature_sharpening"]
            ),
        )
        return graph_artifact, exact_inference_artifact, runtime_snapshot


    def _build_node_score_by_course_node_id(
        self,
        graph_artifact: GraphArtifact,
        runtime_snapshot: RuntimeSnapshot,
    ) -> dict[str, float]:
        return {
            str(node_id): float(runtime_snapshot.node_scores[node_index])
            for node_index, node_id in enumerate(graph_artifact.node_ids)
            if float(runtime_snapshot.node_scores[node_index]) != 0.0
        }


    def _build_assessment_result_payload(
        self,
        test_attempt: TestAttempt,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
    ) -> tuple[GraphStatePayload, float, dict[str, object]]:
        if runtime_state["runtime_kind"] != EXACT_FOREST_RUNTIME_KIND:
            state = self._build_graph_state(graph_version, runtime_state)
            return (
                state,
                self._calculate_state_confidence(state, graph_version),
                {
                    "runtime_kind": runtime_state["runtime_kind"],
                    "answered_count": len(state["answered_course_node_ids"]),
                    "learned_count": len(state["learned_course_node_ids"]),
                    "failed_count": len(state["failed_course_node_ids"]),
                    "node_count": len(graph_version.version_nodes),
                },
            )

        graph_artifact, _, runtime_snapshot = self._build_exact_runtime_context(
            graph_version=graph_version,
            config_snapshot=test_attempt.config_snapshot,
            runtime_state=runtime_state,
        )
        assessment_config = self._get_assessment_config(test_attempt.config_snapshot)
        final_result = build_final_result(
            graph_artifact=graph_artifact,
            runtime=runtime_snapshot,
            learned_mastery_probability=self._get_projected_learned_mastery_probability(
                assessment_config
            ),
            unlearned_mastery_probability=self._get_projected_unlearned_mastery_probability(
                assessment_config
            ),
        )
        state = self._build_exact_graph_state(
            graph_version=graph_version,
            graph_artifact=graph_artifact,
            final_result=final_result,
            runtime_state=runtime_state,
        )
        metadata_json = {
            "runtime_kind": runtime_state["runtime_kind"],
            "state_index": final_result.state_index,
            "state_probability": final_result.state_probability,
            "inner_fringe_course_node_ids": [
                str(course_node_id)
                for course_node_id in final_result.inner_fringe_node_ids
            ],
            "leader_state_probability": runtime_snapshot.leader_state_probability,
            "normalized_entropy": runtime_snapshot.normalized_entropy,
            "answered_count": len(state["answered_course_node_ids"]),
            "learned_count": len(state["learned_course_node_ids"]),
            "failed_count": len(state["failed_course_node_ids"]),
            "node_count": len(graph_version.version_nodes),
        }
        return state, final_result.state_probability, cast("dict[str, object]", metadata_json)


    def _build_exact_graph_state(
        self,
        graph_version: CourseGraphVersion,
        graph_artifact: GraphArtifact,
        final_result: FinalResult,
        runtime_state: TestRuntimeState,
    ) -> GraphStatePayload:
        ordered_course_node_ids = self._build_ordered_course_node_ids(graph_version)
        learned_course_node_ids = set(final_result.learned_node_ids)
        ready_course_node_ids = set(final_result.outer_fringe_node_ids)
        answered_course_node_ids = {
            uuid.UUID(course_node_id)
            for course_node_id in runtime_state["asked_course_node_ids"]
        }
        failed_course_node_ids = answered_course_node_ids - learned_course_node_ids
        locked_course_node_ids = set(ordered_course_node_ids) - learned_course_node_ids - ready_course_node_ids

        return {
            "learned_course_node_ids": [
                str(course_node_id)
                for course_node_id in ordered_course_node_ids
                if course_node_id in learned_course_node_ids
            ],
            "ready_course_node_ids": [
                str(course_node_id)
                for course_node_id in ordered_course_node_ids
                if course_node_id in ready_course_node_ids
            ],
            "locked_course_node_ids": [
                str(course_node_id)
                for course_node_id in ordered_course_node_ids
                if course_node_id in locked_course_node_ids
            ],
            "failed_course_node_ids": [
                str(course_node_id)
                for course_node_id in ordered_course_node_ids
                if course_node_id in failed_course_node_ids
            ],
            "answered_course_node_ids": [
                str(course_node_id)
                for course_node_id in graph_artifact.node_ids
                if course_node_id in answered_course_node_ids
            ],
        }


    def _build_ordered_course_node_ids(
        self,
        graph_version: CourseGraphVersion,
    ) -> list[uuid.UUID]:
        return [
            version_node.course_node_id
            for version_node in sorted(
                graph_version.version_nodes,
                key=lambda version_node: (
                    version_node.topological_rank
                    if version_node.topological_rank is not None
                    else 0,
                    str(version_node.course_node_id),
                ),
            )
        ]


    @staticmethod
    def _map_answer_option_type_to_outcome(
        answer_option_type: ProblemAnswerOptionType,
    ) -> Outcome:
        if answer_option_type == ProblemAnswerOptionType.RIGHT:
            return Outcome.CORRECT
        if answer_option_type == ProblemAnswerOptionType.WRONG:
            return Outcome.INCORRECT
        return Outcome.I_DONT_KNOW


    def _build_graph_state(
        self,
        graph_version: CourseGraphVersion,
        runtime_state: TestRuntimeState,
    ) -> GraphStatePayload:
        asked_course_node_ids = {
            uuid.UUID(course_node_id)
            for course_node_id in runtime_state["asked_course_node_ids"]
        }
        learned_course_node_ids = {
            uuid.UUID(course_node_id)
            for course_node_id in runtime_state["learned_course_node_ids"]
        }
        failed_course_node_ids = {
            uuid.UUID(course_node_id)
            for course_node_id in runtime_state["failed_course_node_ids"]
        }
        prerequisites_by_course_node_id = self._build_prerequisites_by_course_node_id(
            graph_version
        )
        ordered_course_node_ids = self._build_ordered_course_node_ids(graph_version)
        ready_course_node_ids = [
            course_node_id
            for course_node_id in ordered_course_node_ids
            if course_node_id not in asked_course_node_ids
            and prerequisites_by_course_node_id[course_node_id].issubset(learned_course_node_ids)
        ]
        locked_course_node_ids = [
            course_node_id
            for course_node_id in ordered_course_node_ids
            if course_node_id not in asked_course_node_ids
            and course_node_id not in ready_course_node_ids
        ]
        return {
            "learned_course_node_ids": [str(course_node_id) for course_node_id in learned_course_node_ids],
            "ready_course_node_ids": [str(course_node_id) for course_node_id in ready_course_node_ids],
            "locked_course_node_ids": [str(course_node_id) for course_node_id in locked_course_node_ids],
            "failed_course_node_ids": [str(course_node_id) for course_node_id in failed_course_node_ids],
            "answered_course_node_ids": [str(course_node_id) for course_node_id in asked_course_node_ids],
        }


    def _build_prerequisites_by_course_node_id(
        self,
        graph_version: CourseGraphVersion,
    ) -> dict[uuid.UUID, set[uuid.UUID]]:
        prerequisites_by_course_node_id: dict[uuid.UUID, set[uuid.UUID]] = {
            version_node.course_node_id: set()
            for version_node in graph_version.version_nodes
        }
        for edge in graph_version.edges:
            prerequisites_by_course_node_id[edge.dependent_course_node_id].add(
                edge.prerequisite_course_node_id
            )
        return prerequisites_by_course_node_id


    def _find_course_node(
        self,
        graph_version: CourseGraphVersion,
        course_node_id: uuid.UUID,
    ) -> CourseNode:
        version_node = next(
            (
                item
                for item in graph_version.version_nodes
                if item.course_node_id == course_node_id
            ),
            None,
        )
        if version_node is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Course node is not part of this graph version",
            )
        return version_node.course_node


    def _calculate_state_confidence(
        self,
        state: GraphStatePayload,
        graph_version: CourseGraphVersion,
    ) -> float:
        answered_count = len(state["answered_course_node_ids"])
        node_count = len(graph_version.version_nodes)
        if node_count == 0:
            return 1.0
        return answered_count / node_count


    async def _is_perfect_attempt(
        self,
        *,
        session: AsyncSession,
        test_attempt_id: uuid.UUID,
    ) -> bool:
        result = await session.execute(
            select(ResponseEvent.answer_option_type, ResponseEvent.revealed_solution).where(
                ResponseEvent.test_attempt_id == test_attempt_id
            )
        )
        response_rows = result.all()
        if not response_rows:
            return False

        return all(
            answer_option_type == ProblemAnswerOptionType.RIGHT and not revealed_solution
            for answer_option_type, revealed_solution in response_rows
        )


    def _build_review_node_contexts(
        self,
        *,
        graph_version: CourseGraphVersion,
        graph_state: dict[str, object],
        metadata_json: dict[str, object] | None,
    ) -> list[ReviewCourseNodeContext]:
        frontier_node_ids = set(self._read_string_list(metadata_json or {}, "inner_fringe_course_node_ids"))
        if not frontier_node_ids:
            frontier_node_ids = set(
                self._read_string_list(metadata_json or {}, "legacy_frontier_course_node_ids")
            )

        mastery_by_course_node_id: dict[str, str] = {}
        for course_node_id in self._read_string_list(graph_state, "learned_course_node_ids"):
            mastery_by_course_node_id[course_node_id] = "learned"
        for course_node_id in self._read_string_list(graph_state, "ready_course_node_ids"):
            mastery_by_course_node_id.setdefault(course_node_id, "ready")
        for course_node_id in self._read_string_list(graph_state, "failed_course_node_ids"):
            mastery_by_course_node_id.setdefault(course_node_id, "failed")
        for course_node_id in self._read_string_list(graph_state, "locked_course_node_ids"):
            mastery_by_course_node_id.setdefault(course_node_id, "locked")

        return [
            ReviewCourseNodeContext(
                name=version_node.course_node.name,
                description=version_node.course_node.description,
                mastery_state=mastery_by_course_node_id.get(str(version_node.course_node_id), "unknown"),
                is_frontier=str(version_node.course_node_id) in frontier_node_ids,
            )
            for version_node in sorted(
                graph_version.version_nodes,
                key=lambda node: (
                    node.topological_rank if node.topological_rank is not None else 10**9,
                    str(node.course_node_id),
                ),
            )
        ]


    def _build_state_counts(self, state: dict[str, object]) -> dict[str, int]:
        return {
            "learned": len(self._read_string_list(state, "learned_course_node_ids")),
            "ready": len(self._read_string_list(state, "ready_course_node_ids")),
            "locked": len(self._read_string_list(state, "locked_course_node_ids")),
            "failed": len(self._read_string_list(state, "failed_course_node_ids")),
        }


    def _build_deterministic_recommendations(self, state_counts: dict[str, int]) -> list[str]:
        recommendations: list[str] = []
        if state_counts["failed"] > 0:
            recommendations.append("Repeat recently failed problem types in a focused practice run.")
        if state_counts["ready"] > 0:
            recommendations.append("Prioritize ready problem types to unlock additional course sections.")
        if state_counts["locked"] > 0:
            recommendations.append("Strengthen prerequisites before attempting locked problem types.")
        if not recommendations:
            recommendations.append("Continue regular practice to maintain the current mastery state.")
        return recommendations


    def _get_assessment_config(self, config_snapshot: dict[str, object]) -> dict[str, Any]:
        raw_assessment_config = config_snapshot.get("assessment")
        if isinstance(raw_assessment_config, dict):
            return cast("dict[str, Any]", raw_assessment_config)

        logger.warning(
            "Test attempt config snapshot is missing assessment config, using current configuration",
        )
        return cast("dict[str, Any]", get_app_config().entrance_assessment_snapshot())


    @staticmethod
    def _coerce_optional_float(raw_value: Any) -> float | None:
        if raw_value is None:
            return None
        return float(raw_value)


    @staticmethod
    def _get_projected_learned_mastery_probability(
        assessment_config: dict[str, Any],
    ) -> float:
        return float(assessment_config["projected_learned_mastery_probability"])


    @staticmethod
    def _get_projected_unlearned_mastery_probability(
        assessment_config: dict[str, Any],
    ) -> float:
        return float(assessment_config["projected_unlearned_mastery_probability"])


    @staticmethod
    def _get_projection_confidence_stop(
        assessment_config: dict[str, Any],
    ) -> float:
        return float(assessment_config["projection_confidence_stop"])


    @staticmethod
    def _get_frontier_confidence_stop(
        assessment_config: dict[str, Any],
    ) -> float:
        return float(assessment_config["frontier_confidence_stop"])


    def _build_response_model(self, assessment_config: dict[str, Any]) -> ResponseModel:
        raw_response_model = assessment_config.get("response_model")
        if not isinstance(raw_response_model, dict):
            raise RuntimeError("Assessment configuration is missing a response model")

        response_model = ResponseModel(
            mastered_right=self._normalize_probability(raw_response_model["mastered_right"]),
            mastered_wrong=self._normalize_probability(raw_response_model["mastered_wrong"]),
            mastered_i_dont_know=self._normalize_probability(raw_response_model["mastered_i_dont_know"]),
            unmastered_right=self._normalize_probability(raw_response_model["unmastered_right"]),
            unmastered_wrong=self._normalize_probability(raw_response_model["unmastered_wrong"]),
            unmastered_i_dont_know=self._normalize_probability(raw_response_model["unmastered_i_dont_know"]),
        )
        return self._normalize_response_model(response_model)


    @staticmethod
    def _normalize_response_model(response_model: ResponseModel) -> ResponseModel:
        mastered_right, mastered_wrong, mastered_i_dont_know = (
            TestService._normalize_probability_triplet(
                response_model.mastered_right,
                response_model.mastered_wrong,
                response_model.mastered_i_dont_know,
            )
        )
        unmastered_right, unmastered_wrong, unmastered_i_dont_know = (
            TestService._normalize_probability_triplet(
                response_model.unmastered_right,
                response_model.unmastered_wrong,
                response_model.unmastered_i_dont_know,
            )
        )
        return ResponseModel(
            mastered_right=mastered_right,
            mastered_wrong=mastered_wrong,
            mastered_i_dont_know=mastered_i_dont_know,
            unmastered_right=unmastered_right,
            unmastered_wrong=unmastered_wrong,
            unmastered_i_dont_know=unmastered_i_dont_know,
        )


    @staticmethod
    def _normalize_probability_triplet(
        first_value: float,
        second_value: float,
        third_value: float,
    ) -> tuple[float, float, float]:
        total = first_value + second_value + third_value
        if total <= 0.0:
            return 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0

        return (
            first_value / total,
            second_value / total,
            third_value / total,
        )


    @staticmethod
    def _normalize_probability(raw_value: Any) -> float:
        value = float(raw_value)
        return min(max(value, 1e-9), 1.0)
