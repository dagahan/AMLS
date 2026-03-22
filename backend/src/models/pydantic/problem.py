from uuid import UUID

from pydantic import Field, model_validator

from src.storage.db.enums import DifficultyLevel, ProblemAnswerOptionType
from src.models.pydantic.common import AmlsSchema
from src.models.pydantic.difficulty import DifficultyResponse
from src.models.pydantic.problem_type import ProblemTypeResponse
from src.models.pydantic.topic import SubtopicResponse


class ProblemAnswerOptionPayload(AmlsSchema):
    text: str = Field(min_length=1)
    type: ProblemAnswerOptionType


class ProblemCreate(AmlsSchema):
    subtopic_id: UUID
    difficulty: DifficultyLevel
    problem_type_id: UUID
    condition: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    condition_images: list[str] = Field(default_factory=list)
    solution_images: list[str] = Field(default_factory=list)
    answer_options: list[ProblemAnswerOptionPayload]


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemCreate":
        validate_answer_options(self.answer_options)
        return self


class ProblemUpdate(AmlsSchema):
    subtopic_id: UUID | None = None
    difficulty: DifficultyLevel | None = None
    problem_type_id: UUID | None = None
    condition: str | None = Field(default=None, min_length=1)
    solution: str | None = Field(default=None, min_length=1)
    condition_images: list[str] | None = None
    solution_images: list[str] | None = None
    answer_options: list[ProblemAnswerOptionPayload] | None = None


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemUpdate":
        if self.answer_options is not None:
            validate_answer_options(self.answer_options)
        return self


class ProblemAnswerOptionResponse(AmlsSchema):
    id: UUID
    text: str


class AdminProblemAnswerOptionResponse(ProblemAnswerOptionResponse):
    type: ProblemAnswerOptionType


class ProblemResponse(AmlsSchema):
    id: UUID
    subtopic: SubtopicResponse
    difficulty: DifficultyResponse
    problem_type: ProblemTypeResponse
    condition: str
    condition_images: list[str]
    answer_options: list[ProblemAnswerOptionResponse]


class AdminProblemResponse(AmlsSchema):
    id: UUID
    subtopic: SubtopicResponse
    difficulty: DifficultyResponse
    problem_type: ProblemTypeResponse
    condition: str
    condition_images: list[str]
    solution: str
    solution_images: list[str]
    answer_options: list[AdminProblemAnswerOptionResponse]


class ProblemSnapshot(AmlsSchema):
    id: UUID
    subtopic_id: UUID
    difficulty: DifficultyLevel
    problem_type_id: UUID
    condition: str
    solution: str
    condition_images: list[str]
    solution_images: list[str]
    answer_options: list[ProblemAnswerOptionPayload]


def validate_answer_options(answer_options: list[ProblemAnswerOptionPayload]) -> None:
    if not 3 <= len(answer_options) <= 8:
        raise ValueError("Problem must contain from 3 to 8 answer options")

    normalized_options = [item.text.strip() for item in answer_options if item.text.strip()]
    if len(normalized_options) != len(answer_options):
        raise ValueError("Answer options must not be empty")

    if len(set(normalized_options)) != len(answer_options):
        raise ValueError("Answer options must be unique")

    right_options_count = sum(1 for item in answer_options if item.type == ProblemAnswerOptionType.RIGHT)
    if right_options_count != 1:
        raise ValueError("Problem must contain exactly one correct answer option")

    i_dont_know_options_count = sum(
        1
        for item in answer_options
        if item.type == ProblemAnswerOptionType.I_DONT_KNOW
    )
    if i_dont_know_options_count != 1:
        raise ValueError("Problem must contain exactly one I don't know answer option")
