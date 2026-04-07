from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
import json
import uuid
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import get_app_config
from src.core.logging import get_logger
from src.models.alchemy import (
    Course,
    CourseGraphVersion,
    CourseGraphVersionEdge,
    CourseGraphVersionNode,
    CourseNode,
    Lecture,
    LecturePage,
    Problem,
    ProblemType,
    ProblemTypePrerequisite,
    User,
)
from src.storage.db.enums import CourseGraphVersionStatus, UserRole
from src.storage.storage_manager import StorageManager

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


DEMO_COURSE_TITLE = "Profile Mathematics (Grades 10-11)"
DEMO_COURSE_DESCRIPTION = "Single published diploma demo course for profile mathematics grades 10-11."

logger = get_logger(__name__)


class SeedPack(TypedDict):
    version: str
    course_title: str
    course_description: str
    lecture_title_prefix: str


class ProblemSnapshot(TypedDict):
    condition: str
    solution: str


async def bootstrap_demo_course(storage_manager: StorageManager) -> dict[str, object]:
    seed_pack = _load_seed_pack()
    async with storage_manager.session_ctx() as session:
        author = await _load_author_user(session)
        course = await _ensure_course(session, author.id, seed_pack["course_title"])
        graph_version = await _ensure_graph_version(session, course.id)
        problem_types = await _load_problem_types(session)
        node_by_problem_type_id = await _ensure_course_nodes(session, course.id, problem_types)
        version_node_by_course_node_id = await _ensure_graph_version_nodes(
            session=session,
            graph_version=graph_version,
            node_by_problem_type_id=node_by_problem_type_id,
        )
        edge_count, graph_edge_pairs = await _ensure_graph_version_edges(
            session=session,
            graph_version=graph_version,
            node_by_problem_type_id=node_by_problem_type_id,
        )
        topological_rank_by_course_node_id = _build_topological_ranks(
            course_node_ids=list(version_node_by_course_node_id.keys()),
            edges=graph_edge_pairs,
        )
        for course_node_id, version_node in version_node_by_course_node_id.items():
            version_node.topological_rank = topological_rank_by_course_node_id.get(course_node_id)

        lecture_by_course_node_id = await _ensure_lectures(
            session=session,
            course_id=course.id,
            seed_pack=seed_pack,
        )
        for course_node_id, version_node in version_node_by_course_node_id.items():
            lecture = lecture_by_course_node_id.get(course_node_id)
            if lecture is not None:
                version_node.lecture_id = lecture.id

        graph_version.status = CourseGraphVersionStatus.READY
        graph_version.node_count = len(version_node_by_course_node_id)
        graph_version.edge_count = edge_count
        graph_version.built_at = datetime.now(UTC)
        graph_version.error_message = None
        course.current_graph_version_id = graph_version.id
        course.title = seed_pack["course_title"]
        course.description = seed_pack["course_description"]
        await session.flush()
        await session.refresh(graph_version)
        logger.info(
            "Bootstrapped demo course",
            course_id=str(course.id),
            graph_version_id=str(graph_version.id),
            node_count=graph_version.node_count,
            edge_count=graph_version.edge_count,
            lecture_count=len(lecture_by_course_node_id),
            seed_version=seed_pack["version"],
        )
        return {
            "course_id": str(course.id),
            "graph_version_id": str(graph_version.id),
            "node_count": graph_version.node_count,
            "edge_count": graph_version.edge_count,
            "lecture_count": len(lecture_by_course_node_id),
            "seed_version": seed_pack["version"],
        }


def _load_seed_pack() -> SeedPack:
    project_root = get_app_config().project_root
    seed_pack_path = project_root / "backend/src/bootstrap/lecture_seed_pack_v1.json"
    with seed_pack_path.open("r", encoding="utf-8") as seed_pack_file:
        raw_seed_pack = json.load(seed_pack_file)
    if not isinstance(raw_seed_pack, dict):
        raise RuntimeError("Lecture seed pack must be a JSON object")

    return SeedPack(
        version=str(raw_seed_pack.get("version", "v1")),
        course_title=str(raw_seed_pack.get("course_title", DEMO_COURSE_TITLE)),
        course_description=str(
            raw_seed_pack.get("course_description", DEMO_COURSE_DESCRIPTION)
        ),
        lecture_title_prefix=str(raw_seed_pack.get("lecture_title_prefix", "Lecture")),
    )


async def _load_author_user(session: AsyncSession) -> User:
    admin_result = await session.execute(
        select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at.asc(), User.id.asc())
    )
    admin_user = admin_result.scalar_one_or_none()
    if admin_user is not None:
        return admin_user

    user_result = await session.execute(select(User).order_by(User.created_at.asc(), User.id.asc()))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise RuntimeError("Bootstrap requires at least one user in the database")
    return user


async def _ensure_course(session: AsyncSession, author_id: uuid.UUID, title: str) -> Course:
    course_result = await session.execute(
        select(Course).where(Course.title == title).order_by(Course.created_at.asc(), Course.id.asc())
    )
    course = course_result.scalar_one_or_none()
    if course is not None:
        return course

    course = Course(
        author_id=author_id,
        title=title,
        description=DEMO_COURSE_DESCRIPTION,
    )
    session.add(course)
    await session.flush()
    return course


async def _ensure_graph_version(session: AsyncSession, course_id: uuid.UUID) -> CourseGraphVersion:
    graph_version_result = await session.execute(
        select(CourseGraphVersion)
        .options(
            selectinload(CourseGraphVersion.version_nodes),
            selectinload(CourseGraphVersion.edges),
        )
        .where(CourseGraphVersion.course_id == course_id)
        .order_by(CourseGraphVersion.version_number.desc(), CourseGraphVersion.created_at.desc())
    )
    graph_version = graph_version_result.scalars().first()
    if graph_version is not None:
        return graph_version

    graph_version = CourseGraphVersion(
        course_id=course_id,
        version_number=1,
        status=CourseGraphVersionStatus.DRAFT,
        node_count=0,
        edge_count=0,
        built_at=None,
        error_message=None,
    )
    session.add(graph_version)
    await session.flush()
    await session.refresh(graph_version)
    return graph_version


async def _load_problem_types(session: AsyncSession) -> list[ProblemType]:
    result = await session.execute(select(ProblemType).order_by(ProblemType.name.asc()))
    return list(result.scalars().all())


async def _ensure_course_nodes(
    session: AsyncSession,
    course_id: uuid.UUID,
    problem_types: list[ProblemType],
) -> dict[uuid.UUID, CourseNode]:
    existing_result = await session.execute(
        select(CourseNode).where(CourseNode.course_id == course_id).order_by(CourseNode.name.asc())
    )
    existing_nodes = list(existing_result.scalars().all())
    node_by_problem_type_id: dict[uuid.UUID, CourseNode] = {
        node.problem_type_id: node
        for node in existing_nodes
        if node.problem_type_id is not None
    }

    for problem_type in problem_types:
        desired_description = _build_course_node_description(problem_type.name)
        if problem_type.id in node_by_problem_type_id:
            node_by_problem_type_id[problem_type.id].description = desired_description
            continue

        new_node = CourseNode(
            course_id=course_id,
            problem_type_id=problem_type.id,
            name=problem_type.name,
            description=desired_description,
        )
        session.add(new_node)
        await session.flush()
        node_by_problem_type_id[problem_type.id] = new_node

    return node_by_problem_type_id


async def _link_problems_to_course_nodes(
    session: AsyncSession,
    node_by_problem_type_id: dict[uuid.UUID, CourseNode],
) -> None:
    problem_result = await session.execute(select(Problem))
    for problem in problem_result.scalars().all():
        course_node = node_by_problem_type_id.get(problem.problem_type_id)
        if course_node is None:
            continue
        problem.course_node_id = course_node.id


async def _ensure_graph_version_nodes(
    session: AsyncSession,
    graph_version: CourseGraphVersion,
    node_by_problem_type_id: dict[uuid.UUID, CourseNode],
) -> dict[uuid.UUID, CourseGraphVersionNode]:
    existing_result = await session.execute(
        select(CourseGraphVersionNode)
        .where(CourseGraphVersionNode.graph_version_id == graph_version.id)
        .order_by(CourseGraphVersionNode.created_at.asc(), CourseGraphVersionNode.id.asc())
    )
    existing_nodes = list(existing_result.scalars().all())
    version_node_by_course_node_id = {
        version_node.course_node_id: version_node
        for version_node in existing_nodes
    }

    for course_node in node_by_problem_type_id.values():
        if course_node.id in version_node_by_course_node_id:
            continue
        new_version_node = CourseGraphVersionNode(
            graph_version_id=graph_version.id,
            course_node_id=course_node.id,
            lecture_id=None,
            topological_rank=None,
        )
        session.add(new_version_node)
        await session.flush()
        version_node_by_course_node_id[course_node.id] = new_version_node

    return version_node_by_course_node_id


async def _ensure_graph_version_edges(
    session: AsyncSession,
    graph_version: CourseGraphVersion,
    node_by_problem_type_id: dict[uuid.UUID, CourseNode],
) -> tuple[int, list[tuple[uuid.UUID, uuid.UUID]]]:
    existing_result = await session.execute(
        select(CourseGraphVersionEdge)
        .where(CourseGraphVersionEdge.graph_version_id == graph_version.id)
        .order_by(CourseGraphVersionEdge.created_at.asc(), CourseGraphVersionEdge.id.asc())
    )
    existing_edges = list(existing_result.scalars().all())
    existing_edge_pairs = {
        (
            edge.prerequisite_course_node_id,
            edge.dependent_course_node_id,
        )
        for edge in existing_edges
    }
    prerequisite_result = await session.execute(select(ProblemTypePrerequisite))
    prerequisites = list(prerequisite_result.scalars().all())

    for prerequisite in prerequisites:
        prerequisite_node = node_by_problem_type_id.get(prerequisite.prerequisite_problem_type_id)
        dependent_node = node_by_problem_type_id.get(prerequisite.problem_type_id)
        if prerequisite_node is None or dependent_node is None:
            continue
        pair = (prerequisite_node.id, dependent_node.id)
        if pair in existing_edge_pairs:
            continue
        new_edge = CourseGraphVersionEdge(
            graph_version_id=graph_version.id,
            prerequisite_course_node_id=prerequisite_node.id,
            dependent_course_node_id=dependent_node.id,
        )
        session.add(new_edge)
        await session.flush()
        existing_edge_pairs.add(pair)

    refreshed_result = await session.execute(
        select(CourseGraphVersionEdge).where(CourseGraphVersionEdge.graph_version_id == graph_version.id)
    )
    refreshed_edges = list(refreshed_result.scalars().all())
    edge_pairs = [
        (
            edge.prerequisite_course_node_id,
            edge.dependent_course_node_id,
        )
        for edge in refreshed_edges
    ]
    return len(refreshed_edges), edge_pairs


def _build_topological_ranks(
    *,
    course_node_ids: list[uuid.UUID],
    edges: list[tuple[uuid.UUID, uuid.UUID]],
) -> dict[uuid.UUID, int]:
    sorted_course_node_ids = sorted(course_node_ids, key=str)
    dependents_by_node_id: dict[uuid.UUID, list[uuid.UUID]] = {
        course_node_id: []
        for course_node_id in sorted_course_node_ids
    }
    indegree_by_node_id: dict[uuid.UUID, int] = {
        course_node_id: 0
        for course_node_id in sorted_course_node_ids
    }
    for prerequisite_node_id, dependent_node_id in edges:
        if prerequisite_node_id == dependent_node_id:
            continue
        dependents_by_node_id[prerequisite_node_id].append(dependent_node_id)
        indegree_by_node_id[dependent_node_id] += 1

    ready_queue = deque(
        sorted(
            (
                course_node_id
                for course_node_id in sorted_course_node_ids
                if indegree_by_node_id[course_node_id] == 0
            ),
            key=str,
        )
    )
    order: list[uuid.UUID] = []
    while ready_queue:
        current_node_id = ready_queue.popleft()
        order.append(current_node_id)
        for dependent_node_id in sorted(dependents_by_node_id[current_node_id], key=str):
            indegree_by_node_id[dependent_node_id] -= 1
            if indegree_by_node_id[dependent_node_id] == 0:
                ready_queue.append(dependent_node_id)

    if len(order) != len(sorted_course_node_ids):
        order = sorted_course_node_ids

    return {
        course_node_id: rank
        for rank, course_node_id in enumerate(order)
    }


async def _ensure_lectures(
    session: AsyncSession,
    course_id: uuid.UUID,
    seed_pack: SeedPack,
) -> dict[uuid.UUID, Lecture]:
    course_node_result = await session.execute(
        select(CourseNode)
        .options(selectinload(CourseNode.lectures).selectinload(Lecture.pages))
        .where(CourseNode.course_id == course_id)
        .order_by(CourseNode.name.asc(), CourseNode.id.asc())
    )
    course_nodes = list(course_node_result.scalars().all())
    lecture_by_course_node_id: dict[uuid.UUID, Lecture] = {}
    for course_node in course_nodes:
        lecture_page_contents = await _build_lecture_page_contents(
            session=session,
            course_node=course_node,
        )
        lecture = course_node.lectures[0] if course_node.lectures else None
        if lecture is None:
            lecture = Lecture(
                course_node_id=course_node.id,
                title=f"{seed_pack['lecture_title_prefix']}: {course_node.name}",
            )
            session.add(lecture)
            await session.flush()

        lecture.title = f"{seed_pack['lecture_title_prefix']}: {course_node.name}"
        existing_pages_result = await session.execute(
            select(LecturePage)
            .where(LecturePage.lecture_id == lecture.id)
            .order_by(LecturePage.page_number.asc(), LecturePage.id.asc())
        )
        existing_pages = list(existing_pages_result.scalars().all())
        existing_page_by_number = {
            page.page_number: page
            for page in existing_pages
        }
        for page_number, page_content in enumerate(lecture_page_contents, start=1):
            existing_page = existing_page_by_number.get(page_number)
            if existing_page is None:
                lecture_page = LecturePage(
                    lecture_id=lecture.id,
                    page_number=page_number,
                    page_content=page_content,
                )
                session.add(lecture_page)
                continue

            if existing_page.page_content != page_content:
                existing_page.page_content = page_content

        for existing_page in existing_pages:
            if existing_page.page_number > len(lecture_page_contents):
                await session.delete(existing_page)

        await session.flush()

        lecture_by_course_node_id[course_node.id] = lecture

    return lecture_by_course_node_id


def _build_course_node_description(problem_type_name: str) -> str:
    return (
        f"This node develops the skill to {problem_type_name} in profile-mathematics tasks with clear notation and reliable step order. "
        "Focus on method stability, verification of each transformation, and confident final interpretation."
    )


async def _build_lecture_page_contents(
    *,
    session: AsyncSession,
    course_node: CourseNode,
) -> list[str]:
    problem_snapshots = await _load_problem_snapshots_for_course_node(
        session=session,
        course_node=course_node,
        max_items=3,
    )
    first_snapshot = problem_snapshots[0] if problem_snapshots else None
    second_snapshot = problem_snapshots[1] if len(problem_snapshots) > 1 else None
    third_snapshot = problem_snapshots[2] if len(problem_snapshots) > 2 else None

    page_one = (
        f"Core concept: {course_node.name}.\n"
        f"{course_node.description}\n"
        "Target result: identify the governing rule quickly, structure the solution path, and justify the final answer."
    )
    page_two = (
        f"Method framework for {course_node.name}:\n"
        "1. Parse the condition and mark the exact unknown.\n"
        "2. Select the governing transformation or theorem.\n"
        "3. Execute algebraic steps with sign/domain checks.\n"
        "4. Verify the candidate answer in the original condition.\n"
        "5. Write the final conclusion in exam-ready format."
    )
    page_three = (
        f"Worked example for {course_node.name}:\n"
        f"Condition: {first_snapshot['condition'] if first_snapshot is not None else 'No worked example available yet.'}\n"
        f"Solution path: {first_snapshot['solution'] if first_snapshot is not None else 'Add examples to the problem bank for this node.'}"
    )
    practice_lines = [
        f"Practice set for {course_node.name}:",
        (
            f"Task A: {second_snapshot['condition']}"
            if second_snapshot is not None
            else "Task A: Build a new variation with changed numeric values and solve it fully."
        ),
        (
            f"Task B: {third_snapshot['condition']}"
            if third_snapshot is not None
            else "Task B: Solve a parallel exam-style task and compare the final method choice."
        ),
        "Checklist: solution validity, domain restrictions, and concise final answer statement.",
    ]
    page_four = "\n".join(practice_lines)

    return [page_one, page_two, page_three, page_four]


async def _load_problem_snapshots_for_course_node(
    *,
    session: AsyncSession,
    course_node: CourseNode,
    max_items: int,
) -> list[ProblemSnapshot]:
    result = await session.execute(
        select(Problem)
        .where(Problem.course_node_id == course_node.id)
        .order_by(Problem.condition.asc(), Problem.id.asc())
        .limit(max_items)
    )
    direct_problems = list(result.scalars().all())
    if len(direct_problems) < max_items and course_node.problem_type_id is not None:
        fallback_result = await session.execute(
            select(Problem)
            .where(Problem.problem_type_id == course_node.problem_type_id)
            .order_by(Problem.condition.asc(), Problem.id.asc())
            .limit(max_items)
        )
        fallback_problems = list(fallback_result.scalars().all())
        existing_problem_ids = {problem.id for problem in direct_problems}
        for fallback_problem in fallback_problems:
            if fallback_problem.id in existing_problem_ids:
                continue
            direct_problems.append(fallback_problem)
            existing_problem_ids.add(fallback_problem.id)
            if len(direct_problems) >= max_items:
                break

    return [
        ProblemSnapshot(
            condition=problem.condition,
            solution=problem.solution,
        )
        for problem in direct_problems[:max_items]
    ]
