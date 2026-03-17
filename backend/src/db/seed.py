from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from src.core.utils import EnvTools, PasswordTools
from src.db.database import DataBase
from src.db.enums import UserRole
from src.db.models import (
    Difficulty,
    Problem,
    ProblemAnswerOption,
    ProblemSubskill,
    Skill,
    Subskill,
    SubskillPrerequisite,
    Subtopic,
    SubtopicPrerequisite,
    Topic,
    User,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TopicSeedItem:
    name: str
    subtopics: list[str]


@dataclass(frozen=True)
class SkillSeedItem:
    name: str
    subskills: list[str]


@dataclass(frozen=True)
class DifficultySeedItem:
    name: str
    coefficient_beta_bernoulli: float


@dataclass(frozen=True)
class SeedAnswerOption:
    position: int
    text_latex: str
    is_correct: bool


@dataclass(frozen=True)
class SeedProblemSubskill:
    subskill_scope: str
    weight: float


def stable_uuid(scope: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"thesis:{scope}")


def topic_seed() -> list[TopicSeedItem]:
    return [
        TopicSeedItem(
            name="USE No.1 - Planimetry",
            subtopics=[
                "right triangle",
                "tangent, chord, secant",
            ],
        ),
        TopicSeedItem(
            name="USE No.2 - Vectors",
            subtopics=[
                "vector coordinates",
                "scalar product",
            ],
        ),
        TopicSeedItem(
            name="USE No.6 - Elementary equations",
            subtopics=[
                "quadratic equations",
                "logarithmic equations",
            ],
        ),
        TopicSeedItem(
            name="USE No.8 - Derivative and antiderivative",
            subtopics=[
                "geometric meaning of derivative",
                "tangent line",
            ],
        ),
        TopicSeedItem(
            name="USE No.10 - Word problems",
            subtopics=[
                "percentages",
                "motion on water",
            ],
        ),
    ]


def skill_seed() -> list[SkillSeedItem]:
    return [
        SkillSeedItem(
            name="Numbers and expressions",
            subskills=[
                "simplify algebraic fractions",
                "simplify trigonometric expressions",
            ],
        ),
        SkillSeedItem(
            name="Equations",
            subskills=[
                "solve quadratic equations",
                "remove extraneous roots by checking restrictions",
            ],
        ),
        SkillSeedItem(
            name="Planimetry",
            subskills=[
                "solve right-triangle configurations",
                "use tangent, chord, and secant relations",
            ],
        ),
        SkillSeedItem(
            name="Vectors and stereometry",
            subskills=[
                "represent a vector in coordinates",
                "use the scalar product",
            ],
        ),
        SkillSeedItem(
            name="Text and financial modeling",
            subskills=[
                "model percentage problems",
                "model motion on water",
            ],
        ),
    ]


def difficulty_seed() -> list[DifficultySeedItem]:
    return [
        DifficultySeedItem(name="easy", coefficient_beta_bernoulli=0.25),
        DifficultySeedItem(name="medium", coefficient_beta_bernoulli=0.5),
        DifficultySeedItem(name="hard", coefficient_beta_bernoulli=0.75),
    ]


async def upsert_user(session: "AsyncSession") -> None:
    admin_id = stable_uuid("user:admin")
    admin_user = await session.get(User, admin_id)
    if admin_user is None:
        admin_user = User(id=admin_id)
        session.add(admin_user)

    admin_user.email = "admin@example.org"
    admin_user.first_name = "Admin"
    admin_user.last_name = "Thesis"
    admin_user.avatar_url = None
    admin_user.hashed_password = PasswordTools.hash_password("Admin123!")
    admin_user.role = UserRole.ADMIN
    admin_user.is_active = True


async def upsert_topics(session: "AsyncSession") -> None:
    for topic_item in topic_seed():
        topic_name = topic_item.name
        topic_id = stable_uuid(f"topic:{topic_name}")
        topic = await session.get(Topic, topic_id)
        if topic is None:
            topic = Topic(id=topic_id)
            session.add(topic)
        topic.name = topic_name

        for subtopic_name in topic_item.subtopics:
            subtopic_id = stable_uuid(f"subtopic:{topic_name}:{subtopic_name}")
            subtopic = await session.get(Subtopic, subtopic_id)
            if subtopic is None:
                subtopic = Subtopic(id=subtopic_id)
                session.add(subtopic)
            subtopic.topic_id = topic_id
            subtopic.name = subtopic_name

    tangent_line_id = stable_uuid("subtopic:USE No.8 - Derivative and antiderivative:tangent line")
    derivative_meaning_id = stable_uuid(
        "subtopic:USE No.8 - Derivative and antiderivative:geometric meaning of derivative"
    )
    prerequisite_id = stable_uuid("subtopic-prerequisite:tangent-line")
    prerequisite = await session.get(SubtopicPrerequisite, prerequisite_id)
    if prerequisite is None:
        prerequisite = SubtopicPrerequisite(id=prerequisite_id)
        session.add(prerequisite)
    prerequisite.subtopic_id = tangent_line_id
    prerequisite.prerequisite_subtopic_id = derivative_meaning_id
    prerequisite.mastery_weight = 1.0


async def upsert_skills(session: "AsyncSession") -> None:
    for skill_item in skill_seed():
        skill_name = skill_item.name
        skill_id = stable_uuid(f"skill:{skill_name}")
        skill = await session.get(Skill, skill_id)
        if skill is None:
            skill = Skill(id=skill_id)
            session.add(skill)
        skill.name = skill_name

        for subskill_name in skill_item.subskills:
            subskill_id = stable_uuid(f"subskill:{skill_name}:{subskill_name}")
            subskill = await session.get(Subskill, subskill_id)
            if subskill is None:
                subskill = Subskill(id=subskill_id)
                session.add(subskill)
            subskill.skill_id = skill_id
            subskill.name = subskill_name

    scalar_product_id = stable_uuid(
        "subskill:Vectors and stereometry:use the scalar product"
    )
    vector_coordinates_id = stable_uuid(
        "subskill:Vectors and stereometry:represent a vector in coordinates"
    )
    prerequisite_id = stable_uuid("subskill-prerequisite:scalar-product")
    prerequisite = await session.get(SubskillPrerequisite, prerequisite_id)
    if prerequisite is None:
        prerequisite = SubskillPrerequisite(id=prerequisite_id)
        session.add(prerequisite)
    prerequisite.subskill_id = scalar_product_id
    prerequisite.prerequisite_subskill_id = vector_coordinates_id
    prerequisite.mastery_weight = 1.0


async def upsert_difficulties(session: "AsyncSession") -> None:
    for item in difficulty_seed():
        difficulty_name = item.name
        difficulty_id = stable_uuid(f"difficulty:{difficulty_name}")
        difficulty = await session.get(Difficulty, difficulty_id)
        if difficulty is None:
            difficulty = Difficulty(id=difficulty_id)
            session.add(difficulty)
        difficulty.name = difficulty_name
        difficulty.coefficient_beta_bernoulli = item.coefficient_beta_bernoulli


async def replace_problem(
    session: "AsyncSession",
    scope: str,
    subtopic_scope: str,
    difficulty_scope: str,
    condition_latex: str,
    solution_latex: str,
    answer_options: list[SeedAnswerOption],
    subskills: list[SeedProblemSubskill],
) -> None:
    problem_id = stable_uuid(f"problem:{scope}")
    existing_problem = await session.get(Problem, problem_id)
    if existing_problem is not None:
        await session.delete(existing_problem)
        await session.flush()

    problem = Problem(
        id=problem_id,
        subtopic_id=stable_uuid(subtopic_scope),
        difficulty_id=stable_uuid(difficulty_scope),
        condition_latex=condition_latex,
        solution_latex=solution_latex,
        condition_image_urls=[],
        solution_image_urls=[],
    )
    problem.answer_options = [
        ProblemAnswerOption(
            id=stable_uuid(f"answer:{scope}:{index}"),
            position=item.position,
            text_latex=item.text_latex,
            is_correct=item.is_correct,
        )
        for index, item in enumerate(answer_options, start=1)
    ]
    problem.subskill_links = [
        ProblemSubskill(
            subskill_id=stable_uuid(item.subskill_scope),
            weight=item.weight,
        )
        for item in subskills
    ]
    session.add(problem)


async def upsert_problems(session: "AsyncSession") -> None:
    await replace_problem(
        session=session,
        scope="right-triangle-area",
        subtopic_scope="subtopic:USE No.1 - Planimetry:right triangle",
        difficulty_scope="difficulty:easy",
        condition_latex=(
            r"In a right triangle, the legs are 6 and 8. "
            r"Find the area of the triangle."
        ),
        solution_latex=(
            r"The area of a right triangle is \frac{1}{2}ab. "
            r"Therefore, S=\frac{1}{2}\cdot 6 \cdot 8 = 24."
        ),
        answer_options=[
            SeedAnswerOption(position=1, text_latex=r"20", is_correct=False),
            SeedAnswerOption(position=2, text_latex=r"24", is_correct=True),
            SeedAnswerOption(position=3, text_latex=r"28", is_correct=False),
            SeedAnswerOption(position=4, text_latex=r"48", is_correct=False),
        ],
        subskills=[
            SeedProblemSubskill(
                subskill_scope="subskill:Planimetry:solve right-triangle configurations",
                weight=0.8,
            ),
            SeedProblemSubskill(
                subskill_scope="subskill:Numbers and expressions:simplify algebraic fractions",
                weight=0.2,
            ),
        ],
    )
    await replace_problem(
        session=session,
        scope="vector-scalar-product",
        subtopic_scope="subtopic:USE No.2 - Vectors:scalar product",
        difficulty_scope="difficulty:medium",
        condition_latex=(
            r"Given vectors a=(2,-1) and b=(3,4), "
            r"find the scalar product a \cdot b."
        ),
        solution_latex=(
            r"The scalar product equals 2\cdot 3 + (-1)\cdot 4 = 6-4=2."
        ),
        answer_options=[
            SeedAnswerOption(position=1, text_latex=r"-2", is_correct=False),
            SeedAnswerOption(position=2, text_latex=r"2", is_correct=True),
            SeedAnswerOption(position=3, text_latex=r"10", is_correct=False),
            SeedAnswerOption(position=4, text_latex=r"14", is_correct=False),
        ],
        subskills=[
            SeedProblemSubskill(
                subskill_scope="subskill:Vectors and stereometry:represent a vector in coordinates",
                weight=0.4,
            ),
            SeedProblemSubskill(
                subskill_scope="subskill:Vectors and stereometry:use the scalar product",
                weight=0.6,
            ),
        ],
    )
    await replace_problem(
        session=session,
        scope="logarithmic-equation",
        subtopic_scope="subtopic:USE No.6 - Elementary equations:logarithmic equations",
        difficulty_scope="difficulty:hard",
        condition_latex=(
            r"Solve the equation \log_2(x-1)=3."
        ),
        solution_latex=(
            r"From \log_2(x-1)=3 we get x-1=2^3=8, so x=9. "
            r"The restriction x>1 is satisfied."
        ),
        answer_options=[
            SeedAnswerOption(position=1, text_latex=r"7", is_correct=False),
            SeedAnswerOption(position=2, text_latex=r"8", is_correct=False),
            SeedAnswerOption(position=3, text_latex=r"9", is_correct=True),
            SeedAnswerOption(position=4, text_latex=r"10", is_correct=False),
        ],
        subskills=[
            SeedProblemSubskill(
                subskill_scope="subskill:Equations:solve quadratic equations",
                weight=0.3,
            ),
            SeedProblemSubskill(
                subskill_scope="subskill:Equations:remove extraneous roots by checking restrictions",
                weight=0.7,
            ),
        ],
    )
    await replace_problem(
        session=session,
        scope="tangent-line-slope",
        subtopic_scope="subtopic:USE No.8 - Derivative and antiderivative:tangent line",
        difficulty_scope="difficulty:medium",
        condition_latex=(
            r"For f(x)=x^2, find the slope of the tangent line at x=3."
        ),
        solution_latex=(
            r"The derivative is f'(x)=2x. "
            r"At x=3 we have f'(3)=6, so the slope equals 6."
        ),
        answer_options=[
            SeedAnswerOption(position=1, text_latex=r"3", is_correct=False),
            SeedAnswerOption(position=2, text_latex=r"6", is_correct=True),
            SeedAnswerOption(position=3, text_latex=r"9", is_correct=False),
            SeedAnswerOption(position=4, text_latex=r"12", is_correct=False),
        ],
        subskills=[
            SeedProblemSubskill(
                subskill_scope="subskill:Numbers and expressions:simplify algebraic fractions",
                weight=0.2,
            ),
            SeedProblemSubskill(
                subskill_scope="subskill:Equations:solve quadratic equations",
                weight=0.3,
            ),
            SeedProblemSubskill(
                subskill_scope="subskill:Numbers and expressions:simplify trigonometric expressions",
                weight=0.5,
            ),
        ],
    )


async def seed_data() -> None:
    database = DataBase()
    await database.init_alchemy_engine()

    async with database.session_ctx() as session:
        await upsert_user(session)
        await upsert_topics(session)
        await upsert_skills(session)
        await upsert_difficulties(session)
        await upsert_problems(session)
        await session.commit()

    await database.dispose()
    logger.info("Seed data loaded")
    logger.info("Admin credentials: admin@example.org / Admin123!")


if __name__ == "__main__":
    EnvTools.bootstrap_env(service_directory="backend")
    asyncio.run(seed_data())
