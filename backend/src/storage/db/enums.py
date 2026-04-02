from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"


class ProblemAnswerOptionType(StrEnum):
    RIGHT = "right"
    WRONG = "wrong"
    I_DONT_KNOW = "i_dont_know"


class DifficultyLevel(StrEnum):
    ELEMENTARY = "elementary"
    INTERMEDIATE = "intermediate"
    UPPER_INTERMEDIATE = "upper_intermediate"
    ADVANCED = "advanced"
    PROFICIENT = "proficient"


class CourseGraphVersionStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


class TestAttemptKind(StrEnum):
    ENTRANCE = "entrance"
    GENERAL = "general"


class TestAttemptStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
