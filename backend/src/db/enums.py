from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"


class ProblemAnswerOptionType(StrEnum):
    RIGHT = "right"
    WRONG = "wrong"
    I_DONT_KNOW = "i_dont_know"


class EntranceTestStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class EntranceTestStructureStatus(StrEnum):
    READY = "ready"
    FAILED = "failed"


class EntranceTestResultNodeStatus(StrEnum):
    LEARNED = "learned"
    READY = "ready"
    LOCKED = "locked"
