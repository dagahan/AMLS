from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    STUDENT = "student"


class EntranceTestStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    SKIPPED = "skipped"
