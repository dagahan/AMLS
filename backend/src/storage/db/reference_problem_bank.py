from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import delete, func, select

from src.config import bootstrap_config
from src.core.logging import get_logger
from src.storage.db.database import DataBase
from src.storage.db.enums import DifficultyLevel, ProblemAnswerOptionType
from src.storage.db.reference_dataset import PROBLEM_TYPE_DATA
from src.models.alchemy import (
    Problem,
    ProblemAnswerOption,
    ProblemType,
    ResponseEvent,
    Subtopic,
    Topic,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = get_logger(__name__)


class GeneratedAnswerOption(TypedDict):
    text: str
    type: ProblemAnswerOptionType


class GeneratedProblem(TypedDict):
    problem_type_name: str
    topic_name: str
    subtopic_name: str
    difficulty: DifficultyLevel
    condition: str
    solution: str
    answer_options: tuple[GeneratedAnswerOption, ...]


class ProblemBlueprint(TypedDict):
    topic_name: str
    subtopic_name: str
    condition: str
    solution: str
    right_answer_text: str
    wrong_answer_text: str


def build_reference_problem_bank() -> tuple[GeneratedProblem, ...]:
    prerequisite_name_by_problem_type_name = {
        problem_type_name: prerequisite_name
        for problem_type_name, prerequisite_name in PROBLEM_TYPE_DATA
    }
    depth_by_problem_type_name = {
        problem_type_name: _build_problem_type_depth(
            problem_type_name=problem_type_name,
            prerequisite_name_by_problem_type_name=prerequisite_name_by_problem_type_name,
        )
        for problem_type_name, _ in PROBLEM_TYPE_DATA
    }
    generated_problems: list[GeneratedProblem] = []

    for problem_type_name, _ in PROBLEM_TYPE_DATA:
        difficulty_levels = _build_difficulty_levels(
            depth_by_problem_type_name[problem_type_name]
        )
        for variant_index, difficulty_level in enumerate(difficulty_levels):
            blueprint = _build_problem_blueprint(
                problem_type_name=problem_type_name,
                variant_index=variant_index,
            )
            generated_problems.append(
                GeneratedProblem(
                    problem_type_name=problem_type_name,
                    topic_name=blueprint["topic_name"],
                    subtopic_name=blueprint["subtopic_name"],
                    difficulty=difficulty_level,
                    condition=blueprint["condition"],
                    solution=blueprint["solution"],
                    answer_options=(
                        GeneratedAnswerOption(
                            text=blueprint["right_answer_text"],
                            type=ProblemAnswerOptionType.RIGHT,
                        ),
                        GeneratedAnswerOption(
                            text=blueprint["wrong_answer_text"],
                            type=ProblemAnswerOptionType.WRONG,
                        ),
                        GeneratedAnswerOption(
                            text="I don't know",
                            type=ProblemAnswerOptionType.I_DONT_KNOW,
                        ),
                    ),
                )
            )

    logger.info(
        "Built reference problem bank: problem_types={}, generated_problems={}",
        len(PROBLEM_TYPE_DATA),
        len(generated_problems),
    )
    return tuple(generated_problems)


async def load_reference_problem_bank(db: DataBase) -> None:
    generated_problems = build_reference_problem_bank()

    async with db.session_ctx() as session:
        deleted_problem_count = await _count_rows(session, Problem)
        deleted_response_count = await _count_rows(session, ResponseEvent)

        await session.execute(delete(Problem))

        problem_types_by_name = await _load_problem_types_by_name(session)
        subtopic_ids_by_key = await _load_subtopic_ids_by_key(session)

        for generated_problem in generated_problems:
            problem_type = problem_types_by_name[generated_problem["problem_type_name"]]
            subtopic_id = subtopic_ids_by_key[
                (
                    generated_problem["topic_name"],
                    generated_problem["subtopic_name"],
                )
            ]

            problem = Problem(
                subtopic_id=subtopic_id,
                difficulty=generated_problem["difficulty"],
                problem_type_id=problem_type.id,
                condition=generated_problem["condition"],
                solution=generated_problem["solution"],
                condition_images=[],
                solution_images=[],
            )
            problem.answer_options = [
                ProblemAnswerOption(
                    text=answer_option["text"],
                    type=answer_option["type"],
                )
                for answer_option in generated_problem["answer_options"]
            ]
            session.add(problem)

        logger.info(
            "Loaded reference problem bank into database: deleted_problems={}, deleted_responses={}, inserted_problems={}",
            deleted_problem_count,
            deleted_response_count,
            len(generated_problems),
        )


def _build_problem_type_depth(
    problem_type_name: str,
    prerequisite_name_by_problem_type_name: dict[str, str | None],
) -> int:
    prerequisite_name = prerequisite_name_by_problem_type_name[problem_type_name]
    if prerequisite_name is None:
        return 0

    return 1 + _build_problem_type_depth(
        problem_type_name=prerequisite_name,
        prerequisite_name_by_problem_type_name=prerequisite_name_by_problem_type_name,
    )


def _build_difficulty_levels(depth: int) -> tuple[DifficultyLevel, DifficultyLevel, DifficultyLevel]:
    if depth <= 1:
        return (
            DifficultyLevel.INTERMEDIATE,
            DifficultyLevel.UPPER_INTERMEDIATE,
            DifficultyLevel.ADVANCED,
        )
    if depth == 2:
        return (
            DifficultyLevel.UPPER_INTERMEDIATE,
            DifficultyLevel.ADVANCED,
            DifficultyLevel.PROFICIENT,
        )
    return (
        DifficultyLevel.ADVANCED,
        DifficultyLevel.PROFICIENT,
        DifficultyLevel.PROFICIENT,
    )


def _build_additional_variant_blueprint(
    *,
    problem_type_name: str,
    base_blueprint: ProblemBlueprint,
) -> ProblemBlueprint:
    return ProblemBlueprint(
        topic_name=base_blueprint["topic_name"],
        subtopic_name=base_blueprint["subtopic_name"],
        condition=(
            f"{base_blueprint['condition']} "
            f"Then verify the same result using a second method that is valid for {problem_type_name}."
        ),
        solution=(
            f"{base_blueprint['solution']} "
            "The verification step confirms the same final answer and strengthens method reliability."
        ),
        right_answer_text=base_blueprint["right_answer_text"],
        wrong_answer_text=base_blueprint["wrong_answer_text"],
    )


def _build_problem_blueprint(
    problem_type_name: str,
    variant_index: int,
) -> ProblemBlueprint:
    if variant_index >= 2:
        second_variant_blueprint = _build_problem_blueprint(
            problem_type_name=problem_type_name,
            variant_index=1,
        )
        return _build_additional_variant_blueprint(
            problem_type_name=problem_type_name,
            base_blueprint=second_variant_blueprint,
        )

    if problem_type_name == "compare and estimate real numbers":
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of numerical rational expressions",
                prompt="Compare 0.75 and 3/4. Which statement is correct?",
                solution="3/4 equals 0.75, so the numbers are equal.",
                right_answer_text="The numbers are equal",
                wrong_answer_text="0.75 is greater",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of numerical rational expressions",
            prompt="Compare 5/8 and 0.6. Which statement is correct?",
            solution="5/8 equals 0.625, so 5/8 is greater than 0.6.",
            right_answer_text="5/8 is greater",
            wrong_answer_text="0.6 is greater",
        )

    if problem_type_name == "compute with fractions and signed numbers":
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of numerical rational expressions",
                prompt="Compute -6 + 14 / 2.",
                solution="14 / 2 = 7, and -6 + 7 = 1.",
                right_answer_text="1",
                wrong_answer_text="4",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of numerical rational expressions",
            prompt="Compute -9 + 18 / 3.",
            solution="18 / 3 = 6, and -9 + 6 = -3.",
            right_answer_text="-3",
            wrong_answer_text="3",
        )

    if problem_type_name in {
        "convert fractions, decimals, and percentages",
        "model percentage problems",
    }:
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="percentages",
                prompt="What is 35% of 80?",
                solution="0.35 * 80 = 28.",
                right_answer_text="28",
                wrong_answer_text="115",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Word problems",
            subtopic_name="percentages",
            prompt="What is 12.5% of 64?",
            solution="12.5% is 1/8, and 64 / 8 = 8.",
            right_answer_text="8",
            wrong_answer_text="16",
        )

    if problem_type_name in {
        "simplify power expressions",
        "solve exponential equations",
        "solve exponential inequalities",
    }:
        if "inequalities" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="exponential inequalities",
                    prompt="Solve 2^x > 8.",
                    solution="Because 8 = 2^3 and the base is greater than 1, the answer is x > 3.",
                    right_answer_text="x > 3",
                    wrong_answer_text="x < 3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="exponential inequalities",
                prompt="Solve 3^x < 9.",
                solution="Because 9 = 3^2 and the base is greater than 1, the answer is x < 2.",
                right_answer_text="x < 2",
                wrong_answer_text="x > 2",
            )
        if "equations" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="exponential equations",
                    prompt="Solve 2^x = 8.",
                    solution="Because 8 = 2^3, the answer is x = 3.",
                    right_answer_text="x = 3",
                    wrong_answer_text="x = 4",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="exponential equations",
                prompt="Solve 5^x = 25.",
                solution="Because 25 = 5^2, the answer is x = 2.",
                right_answer_text="x = 2",
                wrong_answer_text="x = 5",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="laws of exponents",
                prompt="Compute 2^3 * 2^2.",
                solution="Add exponents: 2^3 * 2^2 = 2^5 = 32.",
                right_answer_text="32",
                wrong_answer_text="64",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="laws of exponents",
            prompt="Compute 3^2 * 3^3.",
            solution="Add exponents: 3^2 * 3^3 = 3^5 = 243.",
            right_answer_text="243",
            wrong_answer_text="729",
        )

    if problem_type_name == "factor algebraic expressions":
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of algebraic expressions and fractions",
                prompt="Factor x^2 - 9.",
                solution="x^2 - 9 is a difference of squares: (x - 3)(x + 3).",
                right_answer_text="(x - 3)(x + 3)",
                wrong_answer_text="(x - 9)(x + 1)",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of algebraic expressions and fractions",
            prompt="Factor x^2 - 16.",
            solution="x^2 - 16 is a difference of squares: (x - 4)(x + 4).",
            right_answer_text="(x - 4)(x + 4)",
            wrong_answer_text="(x - 16)(x + 1)",
        )

    if problem_type_name in {
        "simplify algebraic fractions",
        "solve rational equations",
        "solve rational inequalities by interval method",
    }:
        if "inequalities" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="rational inequalities",
                    prompt="Solve (x - 1) / (x + 2) > 0.",
                    solution="The expression is positive on (-inf, -2) and (1, +inf).",
                    right_answer_text="x < -2 or x > 1",
                    wrong_answer_text="-2 < x < 1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="rational inequalities",
                prompt="Solve (x + 3) / (x - 1) < 0.",
                solution="The expression is negative on (-3, 1).",
                right_answer_text="-3 < x < 1",
                wrong_answer_text="x < -3 or x > 1",
            )
        if "equations" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="rational equations",
                    prompt="Solve 1 / (x - 1) = 1 / 2.",
                    solution="Cross-multiplying gives x - 1 = 2, so x = 3.",
                    right_answer_text="x = 3",
                    wrong_answer_text="x = -1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="rational equations",
                prompt="Solve 3 / x = 1.",
                solution="Multiplying by x gives x = 3.",
                right_answer_text="x = 3",
                wrong_answer_text="x = 1 / 3",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of algebraic expressions and fractions",
                prompt="Simplify (x^2 - 1) / (x - 1), where x is not 1.",
                solution="Factor the numerator: (x - 1)(x + 1) / (x - 1) = x + 1.",
                right_answer_text="x + 1",
                wrong_answer_text="x - 1",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of algebraic expressions and fractions",
            prompt="Simplify (x^2 - 4) / (x - 2), where x is not 2.",
            solution="Factor the numerator: (x - 2)(x + 2) / (x - 2) = x + 2.",
            right_answer_text="x + 2",
            wrong_answer_text="x - 2",
        )

    if problem_type_name in {
        "simplify radical expressions",
        "solve irrational equations",
        "solve irrational inequalities",
    }:
        if "inequalities" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="radical inequalities",
                    prompt="Solve sqrt(x - 1) < 3.",
                    solution="The domain is x >= 1, and x - 1 < 9 gives x < 10, so 1 <= x < 10.",
                    right_answer_text="1 <= x < 10",
                    wrong_answer_text="x > 10",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="radical inequalities",
                prompt="Solve sqrt(x + 4) >= 2.",
                solution="The domain is x >= -4, and x + 4 >= 4 gives x >= 0.",
                right_answer_text="x >= 0",
                wrong_answer_text="x >= -4",
            )
        if "equations" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="irrational equations",
                    prompt="Solve sqrt(x + 1) = 3.",
                    solution="Squaring gives x + 1 = 9, so x = 8.",
                    right_answer_text="x = 8",
                    wrong_answer_text="x = 9",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="irrational equations",
                prompt="Solve sqrt(x - 4) = 5.",
                solution="Squaring gives x - 4 = 25, so x = 29.",
                right_answer_text="x = 29",
                wrong_answer_text="x = 21",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of numerical irrational expressions",
                prompt="Simplify sqrt(50).",
                solution="sqrt(50) = sqrt(25 * 2) = 5 * sqrt(2).",
                right_answer_text="5 * sqrt(2)",
                wrong_answer_text="25 * sqrt(2)",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of numerical irrational expressions",
            prompt="Simplify sqrt(72).",
            solution="sqrt(72) = sqrt(36 * 2) = 6 * sqrt(2).",
            right_answer_text="6 * sqrt(2)",
            wrong_answer_text="12 * sqrt(2)",
        )

    if problem_type_name in {
        "simplify logarithmic expressions",
        "solve logarithmic equations",
        "solve logarithmic inequalities",
    }:
        if "inequalities" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="logarithmic inequalities of first and second degree",
                    prompt="Solve log_2(x) > 1.",
                    solution="Because the base is greater than 1, the answer is x > 2.",
                    right_answer_text="x > 2",
                    wrong_answer_text="0 < x < 2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="logarithmic inequalities of first and second degree",
                prompt="Solve log_3(x) < 2.",
                solution="Because the base is greater than 1, the answer is 0 < x < 9.",
                right_answer_text="0 < x < 9",
                wrong_answer_text="x > 9",
            )
        if "equations" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="logarithmic equations",
                    prompt="Solve log_2(x) = 5.",
                    solution="By definition of logarithm, x = 2^5 = 32.",
                    right_answer_text="x = 32",
                    wrong_answer_text="x = 10",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="logarithmic equations",
                prompt="Solve log_3(x) = 2.",
                solution="By definition of logarithm, x = 3^2 = 9.",
                right_answer_text="x = 9",
                wrong_answer_text="x = 6",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of numerical logarithmic expressions",
                prompt="Compute log_2(8).",
                solution="Because 2^3 = 8, the answer is 3.",
                right_answer_text="3",
                wrong_answer_text="4",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of numerical logarithmic expressions",
            prompt="Compute log_5(25).",
            solution="Because 5^2 = 25, the answer is 2.",
            right_answer_text="2",
            wrong_answer_text="5",
        )

    if problem_type_name in {
        "simplify trigonometric expressions",
        "solve trigonometric equations",
        "solve trigonometric inequalities",
    }:
        if "inequalities" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="trigonometric inequalities",
                    prompt="On the interval (0, 2pi), where is sin(x) positive?",
                    solution="sin(x) is positive on (0, pi).",
                    right_answer_text="0 < x < pi",
                    wrong_answer_text="pi < x < 2pi",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="trigonometric inequalities",
                prompt="On the interval (0, 2pi), where is cos(x) positive?",
                solution="cos(x) is positive on (0, pi/2) and (3pi/2, 2pi).",
                right_answer_text="0 < x < pi/2 or 3pi/2 < x < 2pi",
                wrong_answer_text="pi/2 < x < 3pi/2",
            )
        if "equations" in problem_type_name:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="trigonometric equations",
                    prompt="How many solutions does sin(x) = 0 have on [0, 2pi]?",
                    solution="The solutions are x = 0, pi, 2pi, so there are 3 solutions.",
                    right_answer_text="3",
                    wrong_answer_text="2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="trigonometric equations",
                prompt="How many solutions does cos(x) = 1 have on [0, 2pi]?",
                solution="The solutions are x = 0 and 2pi, so there are 2 solutions.",
                right_answer_text="2",
                wrong_answer_text="1",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Computation and algebraic transformations",
                subtopic_name="transformations of numerical trigonometric expressions",
                prompt="Compute sin(pi / 6).",
                solution="sin(pi / 6) = 1 / 2.",
                right_answer_text="1 / 2",
                wrong_answer_text="sqrt(3) / 2",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Computation and algebraic transformations",
            subtopic_name="transformations of numerical trigonometric expressions",
            prompt="Compute cos(0).",
            solution="cos(0) = 1.",
            right_answer_text="1",
            wrong_answer_text="0",
        )

    if problem_type_name in {
        "solve linear equations",
        "solve systems of equations",
        "solve linear inequalities",
        "solve systems of inequalities",
        "solve inequalities with modulus",
    }:
        if problem_type_name == "solve linear equations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="linear equations",
                    prompt="Solve x + 7 = 19.",
                    solution="Subtract 7 from both sides to get x = 12.",
                    right_answer_text="x = 12",
                    wrong_answer_text="x = 26",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="linear equations",
                prompt="Solve 3x = 18.",
                solution="Divide both sides by 3 to get x = 6.",
                right_answer_text="x = 6",
                wrong_answer_text="x = 15",
            )
        if problem_type_name == "solve systems of equations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="linear equations",
                    prompt="Solve the system x + y = 7 and x - y = 1. Find x.",
                    solution="Adding the equations gives 2x = 8, so x = 4.",
                    right_answer_text="x = 4",
                    wrong_answer_text="x = 3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="linear equations",
                prompt="Solve the system x + y = 10 and x - y = 2. Find y.",
                    solution="Subtracting gives 2y = 8, so y = 4.",
                right_answer_text="y = 4",
                wrong_answer_text="y = 6",
            )
        if problem_type_name == "solve linear inequalities":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="other mixed-type inequalities",
                    prompt="Solve x - 4 > 3.",
                    solution="Add 4 to both sides to get x > 7.",
                    right_answer_text="x > 7",
                    wrong_answer_text="x < 7",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="other mixed-type inequalities",
                prompt="Solve 2x <= 8.",
                solution="Divide both sides by 2 to get x <= 4.",
                right_answer_text="x <= 4",
                wrong_answer_text="x >= 4",
            )
        if problem_type_name == "solve systems of inequalities":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Inequalities",
                    subtopic_name="other mixed-type inequalities",
                    prompt="Solve the system x > 2 and x < 5.",
                    solution="Both conditions hold together on the interval (2, 5).",
                    right_answer_text="2 < x < 5",
                    wrong_answer_text="x < 2 or x > 5",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="other mixed-type inequalities",
                prompt="Solve the system x >= -1 and x < 3.",
                solution="Both conditions hold together on the interval [-1, 3).",
                right_answer_text="-1 <= x < 3",
                wrong_answer_text="x < -1 or x >= 3",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="inequalities with modulus",
                prompt="Solve |x| < 3.",
                solution="The inequality means -3 < x < 3.",
                right_answer_text="-3 < x < 3",
                wrong_answer_text="x < -3 or x > 3",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Inequalities",
            subtopic_name="inequalities with modulus",
            prompt="Solve |x - 2| <= 1.",
            solution="The inequality means 1 <= x <= 3.",
            right_answer_text="1 <= x <= 3",
            wrong_answer_text="x <= 1 or x >= 3",
        )

    if problem_type_name in {
        "solve quadratic equations by factoring",
        "solve quadratic equations by discriminant",
        "analyze the location of roots of a quadratic",
        "solve quadratic inequalities",
    }:
        if problem_type_name == "solve quadratic equations by factoring":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="quadratic equations",
                    prompt="Solve x^2 - 9x = 0. Find the larger root.",
                    solution="Factor: x(x - 9) = 0, so the roots are 0 and 9.",
                    right_answer_text="9",
                    wrong_answer_text="3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="quadratic equations",
                prompt="Solve x^2 - 5x + 6 = 0. Find the smaller root.",
                solution="Factor: (x - 2)(x - 3) = 0, so the roots are 2 and 3.",
                right_answer_text="2",
                wrong_answer_text="1",
            )
        if problem_type_name == "solve quadratic equations by discriminant":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Elementary equations",
                    subtopic_name="quadratic equations",
                    prompt="For x^2 - 7x + 10 = 0, what is the discriminant?",
                    solution="D = 49 - 40 = 9.",
                    right_answer_text="9",
                    wrong_answer_text="11",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Elementary equations",
                subtopic_name="quadratic equations",
                prompt="For x^2 - 5x + 6 = 0, what is the discriminant?",
                solution="D = 25 - 24 = 1.",
                right_answer_text="1",
                wrong_answer_text="5",
            )
        if problem_type_name == "analyze the location of roots of a quadratic":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="location of roots of a quadratic trinomial",
                    prompt="How many real roots does x^2 - 4x + 3 = 0 have?",
                    solution="The discriminant is positive, so there are two real roots.",
                    right_answer_text="2 real roots",
                    wrong_answer_text="0 real roots",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="location of roots of a quadratic trinomial",
                prompt="How many real roots does x^2 + 2x + 1 = 0 have?",
                solution="The discriminant is zero, so there is one repeated real root.",
                right_answer_text="1 real root",
                wrong_answer_text="2 real roots",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Inequalities",
                subtopic_name="rational inequalities",
                prompt="Solve x^2 - 4 < 0.",
                solution="The expression is negative between the roots -2 and 2.",
                right_answer_text="-2 < x < 2",
                wrong_answer_text="x < -2 or x > 2",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Inequalities",
            subtopic_name="rational inequalities",
            prompt="Solve x^2 - 9 >= 0.",
            solution="The expression is nonnegative outside the roots -3 and 3.",
            right_answer_text="x <= -3 or x >= 3",
            wrong_answer_text="-3 <= x <= 3",
        )

    if problem_type_name in {
        "find the domain of a function",
        "read values and properties from a graph",
        "recognize graphs of standard functions",
        "apply graph transformations",
        "determine intervals of increase and decrease",
        "find extrema of a function",
        "find greatest or least value on an interval",
        "read tables, charts, and statistical data",
    }:
        if problem_type_name == "find the domain of a function":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Graphs of functions",
                    subtopic_name="linear functions",
                    prompt="Find the domain of 1 / (x - 3).",
                    solution="The denominator cannot be zero, so x is not equal to 3.",
                    right_answer_text="All real x except 3",
                    wrong_answer_text="All real x",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Graphs of functions",
                subtopic_name="root functions",
                prompt="Find the domain of sqrt(x + 2).",
                solution="The radicand must be nonnegative, so x >= -2.",
                right_answer_text="x >= -2",
                wrong_answer_text="x > 2",
            )
        if problem_type_name == "read values and properties from a graph":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Graphs of functions",
                    subtopic_name="combined / mixed graph-identification tasks",
                    prompt="A graph passes through the point (2, 5). Which statement is correct?",
                    solution="If the point (2, 5) is on the graph, then f(2) = 5.",
                    right_answer_text="f(2) = 5",
                    wrong_answer_text="f(5) = 2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Graphs of functions",
                subtopic_name="combined / mixed graph-identification tasks",
                prompt="A graph intersects the y-axis at y = -3. Which statement is correct?",
                solution="At the y-axis, x = 0, so f(0) = -3.",
                right_answer_text="f(0) = -3",
                wrong_answer_text="f(-3) = 0",
            )
        if problem_type_name == "recognize graphs of standard functions":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Graphs of functions",
                    subtopic_name="parabolas",
                    prompt="Which formula describes a parabola opening upward?",
                    solution="The graph of y = x^2 is a parabola opening upward.",
                    right_answer_text="y = x^2",
                    wrong_answer_text="y = 1 / x",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Graphs of functions",
                subtopic_name="exponential functions",
                prompt="Which formula describes an exponential function?",
                solution="The graph of y = 2^x is exponential.",
                right_answer_text="y = 2^x",
                wrong_answer_text="y = x^2",
            )
        if problem_type_name == "apply graph transformations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Graphs of functions",
                    subtopic_name="combined / mixed graph-identification tasks",
                    prompt="If y = x^2 is shifted 3 units to the right, which formula do we get?",
                    solution="A shift 3 units right replaces x with x - 3.",
                    right_answer_text="y = (x - 3)^2",
                    wrong_answer_text="y = (x + 3)^2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Graphs of functions",
                subtopic_name="combined / mixed graph-identification tasks",
                prompt="If y = sqrt(x) is shifted 2 units up, which formula do we get?",
                solution="A shift 2 units up adds 2 to the function value.",
                right_answer_text="y = sqrt(x) + 2",
                wrong_answer_text="y = sqrt(x + 2)",
            )
        if problem_type_name == "determine intervals of increase and decrease":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Greatest / least value of a function",
                    subtopic_name="investigation without derivative",
                    prompt="On which interval is y = 2x + 1 increasing?",
                    solution="A linear function with positive slope increases on all real numbers.",
                    right_answer_text="On all real numbers",
                    wrong_answer_text="Only for x > 0",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Greatest / least value of a function",
                subtopic_name="investigation without derivative",
                prompt="On which interval is y = -x decreasing?",
                solution="A linear function with negative slope decreases on all real numbers.",
                right_answer_text="On all real numbers",
                wrong_answer_text="Only for x < 0",
            )
        if problem_type_name == "find extrema of a function":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Greatest / least value of a function",
                    subtopic_name="power functions",
                    prompt="What is the maximum value of y = -(x - 2)^2 + 5?",
                    solution="The vertex is at (2, 5), so the maximum value is 5.",
                    right_answer_text="5",
                    wrong_answer_text="2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Greatest / least value of a function",
                subtopic_name="power functions",
                prompt="What is the minimum value of y = (x + 1)^2 - 4?",
                solution="The vertex is at (-1, -4), so the minimum value is -4.",
                right_answer_text="-4",
                wrong_answer_text="4",
            )
        if problem_type_name == "find greatest or least value on an interval":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Greatest / least value of a function",
                    subtopic_name="power functions",
                    prompt="Find the least value of y = x^2 on the interval [-2, 3].",
                    solution="The value 0 is reached at x = 0, which lies in the interval.",
                    right_answer_text="0",
                    wrong_answer_text="4",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Greatest / least value of a function",
                subtopic_name="power functions",
                prompt="Find the greatest value of y = x^2 on the interval [-2, 3].",
                solution="The endpoint x = 3 gives the greatest value 9.",
                right_answer_text="9",
                wrong_answer_text="4",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Basic probability",
                subtopic_name="direct probability from a table / simple selection model",
                prompt="The data values are 3, 5, and 7. What is their arithmetic mean?",
                solution="The mean is (3 + 5 + 7) / 3 = 5.",
                right_answer_text="5",
                wrong_answer_text="15",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Basic probability",
            subtopic_name="direct probability from a table / simple selection model",
            prompt="The table entries are 2, 4, and 8. What is their sum?",
            solution="The sum is 2 + 4 + 8 = 14.",
            right_answer_text="14",
            wrong_answer_text="8",
        )

    if problem_type_name in {
        "use the geometric meaning of the derivative",
        "write the tangent-line equation",
        "use the derivative to investigate a function",
        "use the physical meaning of the derivative",
        "use an antiderivative to find area",
    }:
        if problem_type_name == "use the geometric meaning of the derivative":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Derivative and antiderivative",
                    subtopic_name="geometric meaning of derivative",
                    prompt="If f'(2) = 3, what is the slope of the tangent at x = 2?",
                    solution="The derivative at a point equals the tangent slope there.",
                    right_answer_text="3",
                    wrong_answer_text="2",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Derivative and antiderivative",
                subtopic_name="geometric meaning of derivative",
                prompt="If f'(1) = -4, what is the slope of the tangent at x = 1?",
                solution="The derivative at a point equals the tangent slope there.",
                right_answer_text="-4",
                wrong_answer_text="4",
            )
        if problem_type_name == "write the tangent-line equation":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Derivative and antiderivative",
                    subtopic_name="tangent line",
                    prompt="For y = x^2 at x = 1, which tangent line passes through (1, 1) with slope 2?",
                    solution="Using point-slope form gives y - 1 = 2(x - 1), so y = 2x - 1.",
                    right_answer_text="y = 2x - 1",
                    wrong_answer_text="y = 2x + 1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Derivative and antiderivative",
                subtopic_name="tangent line",
                prompt="A tangent line has slope 3 and passes through (2, 5). Which equation is correct?",
                solution="Using point-slope form gives y - 5 = 3(x - 2), so y = 3x - 1.",
                right_answer_text="y = 3x - 1",
                wrong_answer_text="y = 3x + 1",
            )
        if problem_type_name == "use the derivative to investigate a function":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Derivative and antiderivative",
                    subtopic_name="using derivative to investigate a function",
                    prompt="If f'(x) > 0 on an interval, what can we conclude about f on that interval?",
                    solution="A positive derivative means the function is increasing.",
                    right_answer_text="The function is increasing",
                    wrong_answer_text="The function is decreasing",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Derivative and antiderivative",
                subtopic_name="using derivative to investigate a function",
                prompt="If f'(x) < 0 on an interval, what can we conclude about f on that interval?",
                solution="A negative derivative means the function is decreasing.",
                right_answer_text="The function is decreasing",
                wrong_answer_text="The function is increasing",
            )
        if problem_type_name == "use the physical meaning of the derivative":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Derivative and antiderivative",
                    subtopic_name="physical meaning of derivative",
                    prompt="If s'(t) = 5, what does that mean physically?",
                    solution="The derivative of position is instantaneous velocity, so the speed is 5 units per time.",
                    right_answer_text="Instantaneous speed is 5",
                    wrong_answer_text="Total distance is 5",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Derivative and antiderivative",
                subtopic_name="physical meaning of derivative",
                prompt="If temperature T'(t) = -2, what does that mean physically?",
                solution="The temperature decreases by 2 units per unit time at that moment.",
                right_answer_text="The temperature is decreasing at rate 2",
                wrong_answer_text="The temperature equals -2",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Derivative and antiderivative",
                subtopic_name="basic integral / area of a curvilinear trapezoid",
                prompt="Compute the area under y = 2x from x = 0 to x = 1.",
                solution="The integral of 2x from 0 to 1 equals x^2 from 0 to 1, which is 1.",
                right_answer_text="1",
                wrong_answer_text="2",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Derivative and antiderivative",
            subtopic_name="basic integral / area of a curvilinear trapezoid",
            prompt="Compute the area under y = x from x = 0 to x = 2.",
            solution="The integral of x from 0 to 2 equals x^2 / 2 from 0 to 2, which is 2.",
            right_answer_text="2",
            wrong_answer_text="4",
        )

    if problem_type_name in {
        "calculate compound growth of a deposit",
        "model loan repayment",
        "compare financial plans and choose the optimum",
        "model mixture and alloy problems",
        "model motion on a line",
        "model motion on water",
        "model work-rate problems",
        "solve sequence and progression problems",
        "model progression-based word problems",
    }:
        if problem_type_name == "calculate compound growth of a deposit":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Financial mathematics",
                    subtopic_name="deposits / savings / capitalization",
                    prompt="A deposit of 100 grows by 10% over one period. What is the new amount?",
                    solution="After a 10% increase, the amount becomes 100 * 1.1 = 110.",
                    right_answer_text="110",
                    wrong_answer_text="1000",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Financial mathematics",
                subtopic_name="deposits / savings / capitalization",
                prompt="A deposit of 200 grows by 5% over one period. What is the new amount?",
                solution="After a 5% increase, the amount becomes 200 * 1.05 = 210.",
                right_answer_text="210",
                wrong_answer_text="205",
            )
        if problem_type_name == "model loan repayment":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Financial mathematics",
                    subtopic_name="loans / credits",
                    prompt="A loan balance is 100, and 40 is repaid. What balance remains?",
                    solution="The remaining balance is 100 - 40 = 60.",
                    right_answer_text="60",
                    wrong_answer_text="140",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Financial mathematics",
                subtopic_name="loans / credits",
                prompt="A loan balance is 250, and 70 is repaid. What balance remains?",
                solution="The remaining balance is 250 - 70 = 180.",
                right_answer_text="180",
                wrong_answer_text="320",
            )
        if problem_type_name == "compare financial plans and choose the optimum":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Financial mathematics",
                    subtopic_name="optimal choice between tariffs / plans",
                    prompt="Plan A costs 900 and Plan B costs 950. Which plan is cheaper?",
                    solution="900 is less than 950, so Plan A is cheaper.",
                    right_answer_text="Plan A",
                    wrong_answer_text="Plan B",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Financial mathematics",
                subtopic_name="optimal choice between tariffs / plans",
                prompt="Plan A costs 1200 and Plan B costs 1180. Which plan is cheaper?",
                solution="1180 is less than 1200, so Plan B is cheaper.",
                right_answer_text="Plan B",
                wrong_answer_text="Plan A",
            )
        if problem_type_name == "model mixture and alloy problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Word problems",
                    subtopic_name="alloys and mixtures",
                    prompt="How much pure substance is in 10 kg of a 30% solution?",
                    solution="30% of 10 kg is 3 kg.",
                    right_answer_text="3 kg",
                    wrong_answer_text="7 kg",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="alloys and mixtures",
                prompt="How much pure substance is in 20 kg of a 15% solution?",
                solution="15% of 20 kg is 3 kg.",
                right_answer_text="3 kg",
                wrong_answer_text="17 kg",
            )
        if problem_type_name == "model motion on a line":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Word problems",
                    subtopic_name="motion on a line",
                    prompt="A car travels at 60 km/h for 2 hours. What distance does it cover?",
                    solution="Distance equals speed times time: 60 * 2 = 120 km.",
                    right_answer_text="120 km",
                    wrong_answer_text="30 km",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="motion on a line",
                prompt="A cyclist travels at 15 km/h for 4 hours. What distance does the cyclist cover?",
                solution="Distance equals speed times time: 15 * 4 = 60 km.",
                right_answer_text="60 km",
                wrong_answer_text="19 km",
            )
        if problem_type_name == "model motion on water":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Word problems",
                    subtopic_name="motion on water",
                    prompt="A boat moves at 10 km/h in still water and the current is 2 km/h. What is the downstream speed?",
                    solution="Downstream speed equals 10 + 2 = 12 km/h.",
                    right_answer_text="12 km/h",
                    wrong_answer_text="8 km/h",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="motion on water",
                prompt="A boat moves at 14 km/h in still water and the current is 3 km/h. What is the upstream speed?",
                solution="Upstream speed equals 14 - 3 = 11 km/h.",
                right_answer_text="11 km/h",
                wrong_answer_text="17 km/h",
            )
        if problem_type_name == "model work-rate problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Word problems",
                    subtopic_name="joint work / productivity",
                    prompt="If one worker completes a job in 6 hours, what fraction of the job is done in one hour?",
                    solution="The worker completes 1/6 of the job each hour.",
                    right_answer_text="1/6 of the job",
                    wrong_answer_text="6 jobs",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="joint work / productivity",
                prompt="If one worker completes a job in 4 hours, what fraction of the job is done in one hour?",
                solution="The worker completes 1/4 of the job each hour.",
                right_answer_text="1/4 of the job",
                wrong_answer_text="4 jobs",
            )
        if problem_type_name == "solve sequence and progression problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Word problems",
                    subtopic_name="progressions in context",
                    prompt="An arithmetic progression has first term 2 and common difference 3. What is the third term?",
                    solution="The terms are 2, 5, 8, so the third term is 8.",
                    right_answer_text="8",
                    wrong_answer_text="11",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Word problems",
                subtopic_name="progressions in context",
                prompt="An arithmetic progression has first term 5 and common difference 4. What is the fourth term?",
                solution="The terms are 5, 9, 13, 17, so the fourth term is 17.",
                right_answer_text="17",
                wrong_answer_text="21",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Word problems",
            subtopic_name="progressions in context",
            prompt="A quantity forms an arithmetic progression with first term 10 and difference 5. What is the fifth term?",
            solution="The fifth term equals 10 + 4 * 5 = 30.",
            right_answer_text="30",
            wrong_answer_text="25",
        )

    if problem_type_name in {
        "count elementary outcomes",
        "count permutations and combinations",
        "compute classical probability",
        "use complement probability",
        "use addition of probabilities",
        "use multiplication of probabilities",
        "work with independent events",
        "work with conditional probability",
        "solve repeated-trial probability problems",
    }:
        if problem_type_name == "count elementary outcomes":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Basic probability",
                    subtopic_name="equally likely outcomes",
                    prompt="How many elementary outcomes are there when one standard die is rolled?",
                    solution="A standard die has 6 faces, so there are 6 outcomes.",
                    right_answer_text="6",
                    wrong_answer_text="12",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Basic probability",
                subtopic_name="equally likely outcomes",
                prompt="How many elementary outcomes are there when one coin is tossed?",
                solution="A coin has 2 outcomes: heads and tails.",
                right_answer_text="2",
                wrong_answer_text="4",
            )
        if problem_type_name == "count permutations and combinations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Basic probability",
                    subtopic_name="simple combinatorial counting inside probability",
                    prompt="How many ways can 2 objects be chosen from 4 objects?",
                    solution="The number of combinations is C(4, 2) = 6.",
                    right_answer_text="6",
                    wrong_answer_text="8",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Basic probability",
                subtopic_name="simple combinatorial counting inside probability",
                prompt="How many ways can 2 objects be arranged in order from 3 distinct objects?",
                    solution="The number of ordered arrangements is 3 * 2 = 6.",
                right_answer_text="6",
                wrong_answer_text="3",
            )
        if problem_type_name == "compute classical probability":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Basic probability",
                    subtopic_name="classical definition of probability",
                    prompt="What is the probability of rolling an even number on a standard die?",
                    solution="There are 3 even outcomes out of 6, so the probability is 1/2.",
                    right_answer_text="1/2",
                    wrong_answer_text="1/3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Basic probability",
                subtopic_name="classical definition of probability",
                prompt="What is the probability of drawing a red card from a standard deck?",
                solution="Half of the cards are red, so the probability is 1/2.",
                right_answer_text="1/2",
                wrong_answer_text="1/4",
            )
        if problem_type_name == "use complement probability":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Complex probability / probability theorems",
                    subtopic_name="complement event",
                    prompt="If P(A) = 0.3, what is P(not A)?",
                    solution="The complement probability is 1 - 0.3 = 0.7.",
                    right_answer_text="0.7",
                    wrong_answer_text="0.3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Complex probability / probability theorems",
                subtopic_name="complement event",
                prompt="If P(A) = 0.65, what is P(not A)?",
                solution="The complement probability is 1 - 0.65 = 0.35.",
                right_answer_text="0.35",
                wrong_answer_text="0.65",
            )
        if problem_type_name == "use addition of probabilities":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Complex probability / probability theorems",
                    subtopic_name="addition rule for probabilities",
                    prompt="If A and B are disjoint, P(A) = 0.2, and P(B) = 0.3, what is P(A union B)?",
                    solution="For disjoint events, add the probabilities: 0.2 + 0.3 = 0.5.",
                    right_answer_text="0.5",
                    wrong_answer_text="0.06",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Complex probability / probability theorems",
                subtopic_name="addition rule for probabilities",
                prompt="If A and B are disjoint, P(A) = 0.1, and P(B) = 0.4, what is P(A union B)?",
                solution="For disjoint events, add the probabilities: 0.1 + 0.4 = 0.5.",
                right_answer_text="0.5",
                wrong_answer_text="0.04",
            )
        if problem_type_name in {
            "use multiplication of probabilities",
            "work with independent events",
        }:
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Complex probability / probability theorems",
                    subtopic_name="multiplication rule for probabilities",
                    prompt="If events A and B are independent with probabilities 0.2 and 0.5, what is P(A and B)?",
                    solution="For independent events, multiply: 0.2 * 0.5 = 0.1.",
                    right_answer_text="0.1",
                    wrong_answer_text="0.7",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Complex probability / probability theorems",
                subtopic_name="independent events",
                prompt="If events A and B are independent with probabilities 0.4 and 0.3, what is P(A and B)?",
                solution="For independent events, multiply: 0.4 * 0.3 = 0.12.",
                right_answer_text="0.12",
                wrong_answer_text="0.7",
            )
        if problem_type_name == "work with conditional probability":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Complex probability / probability theorems",
                    subtopic_name="conditional probability",
                    prompt="If P(A and B) = 0.2 and P(B) = 0.5, what is P(A | B)?",
                    solution="Conditional probability equals 0.2 / 0.5 = 0.4.",
                    right_answer_text="0.4",
                    wrong_answer_text="0.7",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Complex probability / probability theorems",
                subtopic_name="conditional probability",
                prompt="If P(A and B) = 0.15 and P(B) = 0.3, what is P(A | B)?",
                solution="Conditional probability equals 0.15 / 0.3 = 0.5.",
                    right_answer_text="0.5",
                wrong_answer_text="0.15",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Complex probability / probability theorems",
                subtopic_name="Bernoulli trials / Bernoulli formula",
                prompt="A success has probability 1/2 in each of two independent trials. What is the probability of two successes?",
                solution="Multiply the probabilities: 1/2 * 1/2 = 1/4.",
                right_answer_text="1/4",
                wrong_answer_text="1/2",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Complex probability / probability theorems",
            subtopic_name="Bernoulli trials / Bernoulli formula",
            prompt="A success has probability 1/3 in each of two independent trials. What is the probability of two successes?",
            solution="Multiply the probabilities: 1/3 * 1/3 = 1/9.",
            right_answer_text="1/9",
            wrong_answer_text="2/3",
        )

    if problem_type_name in {
        "solve right-triangle configurations",
        "use triangle congruence",
        "use triangle similarity",
        "use medians, bisectors, and altitudes",
        "solve quadrilateral and trapezoid configurations",
        "use properties of central and inscribed angles",
        "use tangent, chord, and secant relations",
        "use properties of an incircle",
        "use properties of a circumcircle",
        "compute lengths and areas in plane figures",
    }:
        if problem_type_name == "solve right-triangle configurations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="right triangle",
                    prompt="A right triangle has legs 3 and 4. What is the hypotenuse?",
                    solution="By the Pythagorean theorem, the hypotenuse is 5.",
                    right_answer_text="5",
                    wrong_answer_text="7",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="right triangle",
                prompt="A right triangle has legs 5 and 12. What is the hypotenuse?",
                solution="By the Pythagorean theorem, the hypotenuse is 13.",
                right_answer_text="13",
                wrong_answer_text="17",
            )
        if problem_type_name == "use triangle congruence":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="isosceles triangle",
                    prompt="Two triangles have side lengths 3, 4, 5 and 3, 4, 5. What can we conclude?",
                    solution="Equal corresponding side lengths imply congruence.",
                    right_answer_text="The triangles are congruent",
                    wrong_answer_text="The triangles are only similar",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="isosceles triangle",
                prompt="Two triangles have equal side lengths pairwise. What can we conclude?",
                solution="Equal corresponding side lengths imply congruence.",
                right_answer_text="The triangles are congruent",
                wrong_answer_text="Nothing can be concluded",
            )
        if problem_type_name == "use triangle similarity":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="general triangle",
                    prompt="Two similar triangles have scale factor 2. If one side of the smaller triangle is 3, what is the corresponding side of the larger triangle?",
                    solution="Multiply by the scale factor: 3 * 2 = 6.",
                    right_answer_text="6",
                    wrong_answer_text="1.5",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="general triangle",
                prompt="Two similar triangles have scale factor 3. If one side of the smaller triangle is 4, what is the corresponding side of the larger triangle?",
                solution="Multiply by the scale factor: 4 * 3 = 12.",
                right_answer_text="12",
                wrong_answer_text="7",
            )
        if problem_type_name == "use medians, bisectors, and altitudes":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="general triangle",
                    prompt="In an equilateral triangle, which segment is also an altitude to the base?",
                    solution="A median to the base in an equilateral triangle is also an altitude.",
                    right_answer_text="The median to the base",
                    wrong_answer_text="A random side extension",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="general triangle",
                prompt="Which point is the intersection of the angle bisectors of a triangle?",
                solution="The angle bisectors intersect at the incenter.",
                right_answer_text="The incenter",
                wrong_answer_text="The circumcenter",
            )
        if problem_type_name == "solve quadrilateral and trapezoid configurations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="trapezoids",
                    prompt="A rectangle has side lengths 3 and 5. What is its area?",
                    solution="Area equals 3 * 5 = 15.",
                    right_answer_text="15",
                    wrong_answer_text="8",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="parallelograms",
                prompt="A parallelogram has base 6 and height 4. What is its area?",
                solution="Area equals base times height: 6 * 4 = 24.",
                right_answer_text="24",
                wrong_answer_text="10",
            )
        if problem_type_name == "use properties of central and inscribed angles":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="central and inscribed angles",
                    prompt="An inscribed angle subtending an arc is 35 degrees. What is the corresponding central angle?",
                    solution="A central angle is twice the inscribed angle, so it is 70 degrees.",
                    right_answer_text="70 degrees",
                    wrong_answer_text="35 degrees",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="central and inscribed angles",
                prompt="A central angle subtending an arc is 80 degrees. What is an inscribed angle subtending the same arc?",
                solution="An inscribed angle is half the central angle, so it is 40 degrees.",
                right_answer_text="40 degrees",
                wrong_answer_text="80 degrees",
            )
        if problem_type_name == "use tangent, chord, and secant relations":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="tangent, chord, secant",
                    prompt="What is the angle between a radius and a tangent at the point of tangency?",
                    solution="A radius is perpendicular to the tangent at the point of tangency.",
                    right_answer_text="90 degrees",
                    wrong_answer_text="45 degrees",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="tangent, chord, secant",
                prompt="A tangent touches a circle at one point. How many common points do the tangent and circle have?",
                solution="A tangent meets the circle at exactly one point.",
                right_answer_text="1",
                wrong_answer_text="2",
            )
        if problem_type_name == "use properties of an incircle":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="incircle / inscribed circle",
                    prompt="Which point is the center of an incircle of a triangle?",
                    solution="The center of the incircle is the incenter.",
                    right_answer_text="The incenter",
                    wrong_answer_text="The centroid",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="incircle / inscribed circle",
                prompt="The center of the incircle is the intersection of which lines?",
                solution="The incenter is the intersection of the angle bisectors.",
                right_answer_text="The angle bisectors",
                wrong_answer_text="The medians",
            )
        if problem_type_name == "use properties of a circumcircle":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Planimetry",
                    subtopic_name="circumcircle / circumscribed circle",
                    prompt="Where is the circumcenter of a right triangle located?",
                    solution="The circumcenter of a right triangle is at the midpoint of the hypotenuse.",
                    right_answer_text="At the midpoint of the hypotenuse",
                    wrong_answer_text="At the right-angle vertex",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="circumcircle / circumscribed circle",
                prompt="Which lines intersect at the circumcenter of a triangle?",
                solution="The circumcenter is the intersection of the perpendicular bisectors of the sides.",
                right_answer_text="The perpendicular bisectors",
                wrong_answer_text="The angle bisectors",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Planimetry",
                subtopic_name="general triangle",
                prompt="A triangle has base 6 and height 4. What is its area?",
                solution="Area equals base times height divided by 2: 6 * 4 / 2 = 12.",
                right_answer_text="12",
                wrong_answer_text="24",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Planimetry",
            subtopic_name="general triangle",
            prompt="A circle has radius 3. What is its diameter?",
            solution="The diameter is twice the radius, so it equals 6.",
            right_answer_text="6",
            wrong_answer_text="9",
        )

    if problem_type_name in {
        "represent a vector in coordinates",
        "add and subtract vectors",
        "multiply a vector by a scalar",
        "find vector length",
        "use the scalar product",
        "find the angle between vectors",
    }:
        if problem_type_name == "represent a vector in coordinates":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Vectors",
                    subtopic_name="vector coordinates",
                    prompt="What are the coordinates of the vector from (1, 2) to (4, 6)?",
                    solution="Subtract coordinates: (4 - 1, 6 - 2) = (3, 4).",
                    right_answer_text="(3, 4)",
                    wrong_answer_text="(5, 8)",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="vector coordinates",
                prompt="What are the coordinates of the vector from (2, 5) to (7, 9)?",
                solution="Subtract coordinates: (7 - 2, 9 - 5) = (5, 4).",
                right_answer_text="(5, 4)",
                wrong_answer_text="(9, 14)",
            )
        if problem_type_name == "add and subtract vectors":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Vectors",
                    subtopic_name="addition and subtraction of vectors",
                    prompt="Compute (1, 2) + (3, 4).",
                    solution="Add coordinates componentwise to get (4, 6).",
                    right_answer_text="(4, 6)",
                    wrong_answer_text="(3, 8)",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="addition and subtraction of vectors",
                prompt="Compute (5, 1) - (2, 3).",
                solution="Subtract coordinates componentwise to get (3, -2).",
                right_answer_text="(3, -2)",
                wrong_answer_text="(7, 4)",
            )
        if problem_type_name == "multiply a vector by a scalar":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Vectors",
                    subtopic_name="multiplication of a vector by a scalar",
                    prompt="Compute 3 * (2, -1).",
                    solution="Multiply each coordinate by 3 to get (6, -3).",
                    right_answer_text="(6, -3)",
                    wrong_answer_text="(5, -2)",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="multiplication of a vector by a scalar",
                prompt="Compute -2 * (4, 3).",
                solution="Multiply each coordinate by -2 to get (-8, -6).",
                right_answer_text="(-8, -6)",
                wrong_answer_text="(8, 6)",
            )
        if problem_type_name == "find vector length":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Vectors",
                    subtopic_name="vector length",
                    prompt="Find the length of the vector (3, 4).",
                    solution="The length is sqrt(3^2 + 4^2) = 5.",
                    right_answer_text="5",
                    wrong_answer_text="7",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="vector length",
                prompt="Find the length of the vector (5, 12).",
                solution="The length is sqrt(5^2 + 12^2) = 13.",
                right_answer_text="13",
                wrong_answer_text="17",
            )
        if problem_type_name == "use the scalar product":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Vectors",
                    subtopic_name="scalar product",
                    prompt="Compute the scalar product of (1, 2) and (3, 4).",
                    solution="The scalar product is 1 * 3 + 2 * 4 = 11.",
                    right_answer_text="11",
                    wrong_answer_text="10",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="scalar product",
                prompt="Compute the scalar product of (2, -1) and (5, 3).",
                solution="The scalar product is 2 * 5 + (-1) * 3 = 7.",
                right_answer_text="7",
                wrong_answer_text="13",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Vectors",
                subtopic_name="angle between vectors",
                prompt="What is the angle between two perpendicular vectors?",
                solution="Perpendicular vectors form a right angle of 90 degrees.",
                right_answer_text="90 degrees",
                wrong_answer_text="45 degrees",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Vectors",
            subtopic_name="angle between vectors",
            prompt="What is the angle between two collinear vectors pointing in the same direction?",
            solution="Vectors in the same direction form an angle of 0 degrees.",
            right_answer_text="0 degrees",
            wrong_answer_text="180 degrees",
        )

    if problem_type_name in {
        "compute surface area of solids",
        "compute volume of solids",
        "solve sections of prisms and pyramids",
        "find an angle between lines and planes in space",
        "find distances in space",
        "solve combined-solid problems",
    }:
        if problem_type_name == "compute surface area of solids":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Stereometry",
                    subtopic_name="cube",
                    prompt="A cube has side length 2. What is its surface area?",
                    solution="The surface area of a cube is 6a^2 = 6 * 4 = 24.",
                    right_answer_text="24",
                    wrong_answer_text="8",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Stereometry",
                subtopic_name="cube",
                prompt="A cube has side length 3. What is its surface area?",
                solution="The surface area of a cube is 6a^2 = 6 * 9 = 54.",
                right_answer_text="54",
                wrong_answer_text="27",
            )
        if problem_type_name == "compute volume of solids":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Stereometry",
                    subtopic_name="cube",
                    prompt="A cube has side length 3. What is its volume?",
                    solution="The volume of a cube is a^3 = 27.",
                    right_answer_text="27",
                    wrong_answer_text="9",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Stereometry",
                subtopic_name="rectangular parallelepiped / cuboid",
                prompt="A rectangular box has dimensions 2, 3, and 4. What is its volume?",
                solution="The volume is 2 * 3 * 4 = 24.",
                right_answer_text="24",
                wrong_answer_text="9",
            )
        if problem_type_name == "solve sections of prisms and pyramids":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Advanced stereometry",
                    subtopic_name="sections of prisms",
                    prompt="A section of a prism by a plane parallel to the base has what relation to the base?",
                    solution="A section parallel to the base of a prism is congruent to the base.",
                    right_answer_text="It is congruent to the base",
                    wrong_answer_text="It is always a triangle",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Advanced stereometry",
                subtopic_name="sections of pyramids",
                prompt="A section of a pyramid by a plane parallel to the base has what general shape relative to the base?",
                solution="A section parallel to the base of a pyramid is similar to the base.",
                right_answer_text="It is similar to the base",
                wrong_answer_text="It is perpendicular to the base",
            )
        if problem_type_name == "find an angle between lines and planes in space":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Advanced stereometry",
                    subtopic_name="angle between a line and a plane",
                    prompt="What is the angle between a line perpendicular to a plane and that plane?",
                    solution="A line perpendicular to a plane makes a 90-degree angle with the plane.",
                    right_answer_text="90 degrees",
                    wrong_answer_text="0 degrees",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Advanced stereometry",
                subtopic_name="angle between a line and a plane",
                prompt="What is the angle between a line lying in a plane and that plane?",
                solution="A line lying in a plane makes an angle of 0 degrees with the plane.",
                right_answer_text="0 degrees",
                wrong_answer_text="90 degrees",
            )
        if problem_type_name == "find distances in space":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Advanced stereometry",
                    subtopic_name="distance between points; point to line",
                    prompt="What is the distance between the same point and itself in space?",
                    solution="The distance from a point to itself is 0.",
                    right_answer_text="0",
                    wrong_answer_text="1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Advanced stereometry",
                subtopic_name="distance from point to plane",
                prompt="If a point lies on a plane, what is the distance from the point to the plane?",
                solution="A point on the plane has distance 0 from the plane.",
                right_answer_text="0",
                wrong_answer_text="1",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Advanced stereometry",
                subtopic_name="combinations of figures / solids",
                prompt="If two non-overlapping solids have volumes 10 and 15, what is their combined volume?",
                solution="Add the volumes: 10 + 15 = 25.",
                right_answer_text="25",
                wrong_answer_text="5",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Advanced stereometry",
            subtopic_name="combinations of figures / solids",
            prompt="If two non-overlapping solids have volumes 7 and 9, what is their combined volume?",
            solution="Add the volumes: 7 + 9 = 16.",
            right_answer_text="16",
            wrong_answer_text="63",
        )

    if problem_type_name in {
        "solve equations with a parameter",
        "solve inequalities with a parameter",
        "solve systems with a parameter",
        "use monotonicity in parameter problems",
        "use symmetry in parameter problems",
        "use the coordinate plane (x, a) in parameter problems",
    }:
        if problem_type_name == "solve equations with a parameter":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="equations with a parameter",
                    prompt="If x = a + 2 and a = 3, what is x?",
                    solution="Substitute a = 3 to get x = 5.",
                    right_answer_text="5",
                    wrong_answer_text="1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="equations with a parameter",
                prompt="If x = 2a - 1 and a = 4, what is x?",
                solution="Substitute a = 4 to get x = 7.",
                right_answer_text="7",
                wrong_answer_text="5",
            )
        if problem_type_name == "solve inequalities with a parameter":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="inequalities with a parameter",
                    prompt="If x > a and a = 4, which value satisfies the inequality?",
                    solution="Any x greater than 4 works, for example x = 5.",
                    right_answer_text="x = 5",
                    wrong_answer_text="x = 3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="inequalities with a parameter",
                prompt="If x < a and a = -2, which value satisfies the inequality?",
                solution="Any x less than -2 works, for example x = -3.",
                right_answer_text="x = -3",
                wrong_answer_text="x = -1",
            )
        if problem_type_name == "solve systems with a parameter":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="systems with a parameter",
                    prompt="If x = a and y = a + 1 with a = 2, what is x + y?",
                    solution="Substitute a = 2 to get x = 2 and y = 3, so x + y = 5.",
                    right_answer_text="5",
                    wrong_answer_text="4",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="systems with a parameter",
                prompt="If x = a - 1 and y = a + 2 with a = 3, what is y - x?",
                solution="Substitute a = 3 to get x = 2 and y = 5, so y - x = 3.",
                right_answer_text="3",
                wrong_answer_text="7",
            )
        if problem_type_name == "use monotonicity in parameter problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="use of monotonicity and estimates",
                    prompt="If a function is increasing and x1 < x2, which statement is true?",
                    solution="For an increasing function, x1 < x2 implies f(x1) < f(x2).",
                    right_answer_text="f(x1) < f(x2)",
                    wrong_answer_text="f(x1) > f(x2)",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="use of monotonicity and estimates",
                prompt="If a function is decreasing and x1 < x2, which statement is true?",
                solution="For a decreasing function, x1 < x2 implies f(x1) > f(x2).",
                right_answer_text="f(x1) > f(x2)",
                wrong_answer_text="f(x1) < f(x2)",
            )
        if problem_type_name == "use symmetry in parameter problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Problems with a parameter",
                    subtopic_name="use of symmetry",
                    prompt="Which equation is symmetric with respect to replacing x by -x?",
                    solution="The equation x^2 = a is symmetric because squaring removes the sign of x.",
                    right_answer_text="x^2 = a",
                    wrong_answer_text="x = a + 1",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="use of symmetry",
                prompt="If an equation contains only x^2, what pair of roots often appears together?",
                solution="Roots of symmetric equations often appear as opposite numbers.",
                right_answer_text="x and -x",
                wrong_answer_text="x and x + 1",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Problems with a parameter",
                subtopic_name="coordinate-plane method in (x, a)",
                prompt="In the coordinate plane (x, a), what are the coordinates of the point with x = 2 and a = 3?",
                solution="The point is written directly as (2, 3).",
                right_answer_text="(2, 3)",
                wrong_answer_text="(3, 2)",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Problems with a parameter",
            subtopic_name="coordinate-plane method in (x, a)",
            prompt="In the coordinate plane (x, a), what are the coordinates of the point with x = -1 and a = 4?",
            solution="The point is written directly as (-1, 4).",
            right_answer_text="(-1, 4)",
            wrong_answer_text="(4, -1)",
        )

    if problem_type_name in {
        "use prime factorization",
        "find gcd and lcm",
        "prove divisibility statements",
        "use parity arguments",
        "solve remainder problems",
        "analyze digit properties of integers",
    }:
        if problem_type_name == "use prime factorization":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Numbers and their properties",
                    subtopic_name="factorization / fundamental theorem of arithmetic",
                    prompt="What are the prime factors of 12?",
                    solution="12 = 2^2 * 3, so its prime factors are 2 and 3.",
                    right_answer_text="2 and 3",
                    wrong_answer_text="4 and 3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="factorization / fundamental theorem of arithmetic",
                prompt="What are the prime factors of 18?",
                solution="18 = 2 * 3^2, so its prime factors are 2 and 3.",
                right_answer_text="2 and 3",
                wrong_answer_text="6 and 3",
            )
        if problem_type_name == "find gcd and lcm":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Numbers and their properties",
                    subtopic_name="greatest common divisor and least common multiple",
                    prompt="What is the gcd of 12 and 18?",
                    solution="The greatest common divisor of 12 and 18 is 6.",
                    right_answer_text="6",
                    wrong_answer_text="36",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="greatest common divisor and least common multiple",
                prompt="What is the lcm of 4 and 6?",
                solution="The least common multiple of 4 and 6 is 12.",
                right_answer_text="12",
                wrong_answer_text="24",
            )
        if problem_type_name == "prove divisibility statements":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Numbers and their properties",
                    subtopic_name="divisibility",
                    prompt="Which statement is true?",
                    solution="Because 27 = 3 * 9, the number 27 is divisible by 3.",
                    right_answer_text="27 is divisible by 3",
                    wrong_answer_text="27 is divisible by 5",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="divisibility",
                prompt="Which statement is true?",
                solution="Because 42 = 6 * 7, the number 42 is divisible by 6.",
                right_answer_text="42 is divisible by 6",
                wrong_answer_text="42 is divisible by 5",
            )
        if problem_type_name == "use parity arguments":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Numbers and their properties",
                    subtopic_name="parity / odd-even arguments",
                    prompt="What is the parity of even + even?",
                    solution="The sum of two even integers is even.",
                    right_answer_text="Even",
                    wrong_answer_text="Odd",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="parity / odd-even arguments",
                prompt="What is the parity of odd + odd?",
                solution="The sum of two odd integers is even.",
                right_answer_text="Even",
                wrong_answer_text="Odd",
            )
        if problem_type_name == "solve remainder problems":
            if variant_index == 0:
                return _build_blueprint(
                    problem_type_name=problem_type_name,
                    topic_name="Numbers and their properties",
                    subtopic_name="remainders / modular reasoning",
                    prompt="What remainder is obtained when 17 is divided by 5?",
                    solution="17 = 5 * 3 + 2, so the remainder is 2.",
                    right_answer_text="2",
                    wrong_answer_text="3",
                )
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="remainders / modular reasoning",
                prompt="What remainder is obtained when 29 is divided by 6?",
                solution="29 = 6 * 4 + 5, so the remainder is 5.",
                right_answer_text="5",
                wrong_answer_text="4",
            )
        if variant_index == 0:
            return _build_blueprint(
                problem_type_name=problem_type_name,
                topic_name="Numbers and their properties",
                subtopic_name="decimal representation and digit properties",
                prompt="What is the sum of the digits of 123?",
                solution="1 + 2 + 3 = 6.",
                right_answer_text="6",
                wrong_answer_text="123",
            )
        return _build_blueprint(
            problem_type_name=problem_type_name,
            topic_name="Numbers and their properties",
            subtopic_name="decimal representation and digit properties",
            prompt="How many digits does the number 507 have?",
            solution="The number 507 has 3 digits.",
            right_answer_text="3",
            wrong_answer_text="2",
        )

    raise ValueError(f"Reference problem blueprint is not defined for '{problem_type_name}'")


def _build_blueprint(
    problem_type_name: str,
    topic_name: str,
    subtopic_name: str,
    prompt: str,
    solution: str,
    right_answer_text: str,
    wrong_answer_text: str,
) -> ProblemBlueprint:
    return ProblemBlueprint(
        topic_name=topic_name,
        subtopic_name=subtopic_name,
        condition=f"{problem_type_name.capitalize()}. {prompt}",
        solution=solution,
        right_answer_text=right_answer_text,
        wrong_answer_text=wrong_answer_text,
    )


async def _count_rows(session: "AsyncSession", model: type[object]) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())




async def _load_problem_types_by_name(
    session: "AsyncSession",
) -> dict[str, ProblemType]:
    result = await session.execute(select(ProblemType))
    return {
        problem_type.name: problem_type
        for problem_type in result.scalars().all()
    }


async def _load_subtopic_ids_by_key(
    session: "AsyncSession",
) -> dict[tuple[str, str], uuid.UUID]:
    result = await session.execute(
        select(Topic.name, Subtopic.name, Subtopic.id)
        .join(Subtopic, Subtopic.topic_id == Topic.id)
    )
    return {
        (topic_name, subtopic_name): subtopic_id
        for topic_name, subtopic_name, subtopic_id in result.all()
    }


async def main() -> None:
    bootstrap_config()
    db = DataBase()
    await db.init_alchemy_engine()
    try:
        await load_reference_problem_bank(db)
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
