from uuid import UUID

from pydantic import Field, model_validator

from src.pydantic_schemas.common import AmlsSchema
from src.pydantic_schemas.difficulty import DifficultyResponse
from src.pydantic_schemas.topic import SubtopicResponse


class ProblemSubskillPayload(AmlsSchema):
    subskill_id: UUID
    weight: float = Field(ge=0, le=1)


class ProblemCreate(AmlsSchema):
    subtopic_id: UUID
    difficulty_id: UUID
    condition: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    condition_images: list[str] = Field(default_factory=list)
    solution_images: list[str] = Field(default_factory=list)
    answer_options: list[str]
    right_answer: str = Field(min_length=1)
    subskills: list[ProblemSubskillPayload]


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemCreate":
        validate_answer_options(self.answer_options, self.right_answer)
        validate_subskills(self.subskills)
        return self


class ProblemUpdate(AmlsSchema):
    subtopic_id: UUID | None = None
    difficulty_id: UUID | None = None
    condition: str | None = Field(default=None, min_length=1)
    solution: str | None = Field(default=None, min_length=1)
    condition_images: list[str] | None = None
    solution_images: list[str] | None = None
    answer_options: list[str] | None = None
    right_answer: str | None = Field(default=None, min_length=1)
    subskills: list[ProblemSubskillPayload] | None = None


    @model_validator(mode="after")
    def validate_payload(self) -> "ProblemUpdate":
        if self.answer_options is not None:
            validate_answer_options(self.answer_options, self.right_answer)
        if self.subskills is not None:
            validate_subskills(self.subskills)
        return self


class ProblemAnswerOptionResponse(AmlsSchema):
    id: UUID
    text: str


class ProblemSubskillResponse(AmlsSchema):
    subskill_id: UUID
    weight: float


class ProblemResponse(AmlsSchema):
    id: UUID
    subtopic: SubtopicResponse
    difficulty: DifficultyResponse
    condition: str
    condition_images: list[str]
    answer_options: list[ProblemAnswerOptionResponse]


class AdminProblemResponse(AmlsSchema):
    id: UUID
    subtopic: SubtopicResponse
    difficulty: DifficultyResponse
    condition: str
    condition_images: list[str]
    solution: str
    solution_images: list[str]
    answer_options: list[ProblemAnswerOptionResponse]
    right_answer: str
    subskills: list[ProblemSubskillResponse]


class ProblemSubmitRequest(AmlsSchema):
    answer_option_id: UUID


class ProblemSubmitResponse(AmlsSchema):
    correct: bool
    solution: str
    solution_images: list[str]


class StudentProgressResponse(AmlsSchema):
    solved_problem_ids: list[UUID]
    failed_problem_ids: list[UUID]


class ProblemSnapshot(AmlsSchema):
    id: UUID
    subtopic_id: UUID
    difficulty_id: UUID
    condition: str
    solution: str
    right_answer: str
    condition_images: list[str]
    solution_images: list[str]
    answer_options: list[str]
    subskills: list[tuple[UUID, float]]


class SubmissionSnapshot(AmlsSchema):
    user_id: UUID
    problem_id: UUID
    solved_exists: bool
    failed_exists: bool


def validate_answer_options(answer_options: list[str], right_answer: str | None) -> None:
    if not 3 <= len(answer_options) <= 8:
        raise ValueError("Problem must contain from 3 to 8 answer options")

    normalized_options = [item.strip() for item in answer_options if item.strip()]
    if len(normalized_options) != len(answer_options):
        raise ValueError("Answer options must not be empty")

    if len(set(answer_options)) != len(answer_options):
        raise ValueError("Answer options must be unique")

    if right_answer is not None and right_answer not in answer_options:
        raise ValueError("Right answer must match one of the answer options")


def validate_subskills(subskills: list[ProblemSubskillPayload]) -> None:
    if not subskills:
        raise ValueError("Problem must contain at least one related subskill")

    total_weight = sum(item.weight for item in subskills)
    if abs(total_weight - 1.0) > 1e-6:
        raise ValueError("Subskill weights must sum to 1")

    subskill_ids = {item.subskill_id for item in subskills}
    if len(subskill_ids) != len(subskills):
        raise ValueError("Problem subskills must be unique")
