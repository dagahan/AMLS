from uuid import UUID

from src.pydantic_schemas.common import AmlsSchema


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


class AvatarSnapshot(AmlsSchema):
    user_id: UUID
    avatar_url: str | None


class StoredFile(AmlsSchema):
    content: bytes
    content_type: str | None
