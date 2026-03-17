from uuid import UUID

from pydantic import Field, model_validator

from src.pydantic_schemas.common import ThesisSchema
from src.pydantic_schemas.difficulty import DifficultyResponse
from src.pydantic_schemas.skill import SubskillResponse
from src.pydantic_schemas.topic import SubtopicResponse


class ProblemAnswerOptionPayload(ThesisSchema):
    position: int = Field(ge=1, le=8)
    text_latex: str = Field(min_length=1)
    is_correct: bool


class ProblemSubskillPayload(ThesisSchema):
    subskill_id: UUID
    weight: float = Field(ge=0, le=1)


class ProblemCreate(ThesisSchema):
    subtopic_id: UUID
    difficulty_id: UUID
    condition_latex: str = Field(min_length=1)
    solution_latex: str = Field(min_length=1)
    condition_image_urls: list[str] = Field(default_factory=list)
    solution_image_urls: list[str] = Field(default_factory=list)
    answer_options: list[ProblemAnswerOptionPayload]
    subskills: list[ProblemSubskillPayload]


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemCreate":
        validate_answer_options(self.answer_options)
        validate_subskills(self.subskills)
        return self


class ProblemUpdate(ThesisSchema):
    subtopic_id: UUID | None = None
    difficulty_id: UUID | None = None
    condition_latex: str | None = Field(default=None, min_length=1)
    solution_latex: str | None = Field(default=None, min_length=1)
    condition_image_urls: list[str] | None = None
    solution_image_urls: list[str] | None = None
    answer_options: list[ProblemAnswerOptionPayload] | None = None
    subskills: list[ProblemSubskillPayload] | None = None


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemUpdate":
        if self.answer_options is not None:
            validate_answer_options(self.answer_options)
        if self.subskills is not None:
            validate_subskills(self.subskills)
        return self


class ProblemAnswerOptionResponse(ThesisSchema):
    id: UUID
    position: int
    text_latex: str
    is_correct: bool


class ProblemSubskillResponse(ThesisSchema):
    subskill: SubskillResponse
    weight: float


class ProblemResponse(ThesisSchema):
    id: UUID
    subtopic: SubtopicResponse
    difficulty: DifficultyResponse
    condition_latex: str
    solution_latex: str
    condition_image_urls: list[str]
    solution_image_urls: list[str]
    answer_options: list[ProblemAnswerOptionResponse]
    subskills: list[ProblemSubskillResponse]


def validate_answer_options(answer_options: list[ProblemAnswerOptionPayload]) -> None:
    if not 3 <= len(answer_options) <= 8:
        raise ValueError("Problem must contain from 3 to 8 answer options")

    correct_answers_count = sum(1 for option in answer_options if option.is_correct)
    if correct_answers_count != 1:
        raise ValueError("Problem must contain exactly one correct answer option")

    positions = {option.position for option in answer_options}
    if len(positions) != len(answer_options):
        raise ValueError("Answer option positions must be unique")


def validate_subskills(subskills: list[ProblemSubskillPayload]) -> None:
    if not subskills:
        raise ValueError("Problem must contain at least one related subskill")

    total_weight = sum(item.weight for item in subskills)
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError("Subskill weights must sum to 1")

    subskill_ids = {item.subskill_id for item in subskills}
    if len(subskill_ids) != len(subskills):
        raise ValueError("Problem subskills must be unique")
