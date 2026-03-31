from __future__ import annotations

from typing import Any

from src.config.config_section import ConfigSection


class DifficultyConfig:
    __slots__ = ("key", "name", "coefficient")

    def __init__(self, key: str, name: str, coefficient: float) -> None:
        self.key = key
        self.name = name
        self.coefficient = coefficient


class EntranceAssessmentConfig(ConfigSection):
    __slots__ = ()

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)


    def snapshot(self) -> dict[str, object]:
        return self._snapshot()


class BusinessConfig(ConfigSection):
    __slots__ = ("_difficulties", "_entrance_assessment")

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)
        self._entrance_assessment = EntranceAssessmentConfig(
            self._require_mapping("entrance_assessment"),
        )
        self._difficulties = self._require_mapping("difficulties")


    @property
    def entrance_assessment(self) -> EntranceAssessmentConfig:
        return self._entrance_assessment


    def difficulty(self, difficulty_key: str) -> DifficultyConfig:
        difficulty_path = f"business.difficulties.{difficulty_key}"
        difficulty_values = self._read_mapping(
            self._difficulties,
            difficulty_key,
            difficulty_path,
        )
        name = self._read_string(difficulty_values, "name", f"{difficulty_path}.name")
        coefficient = self._read_float(
            difficulty_values,
            "coefficient",
            f"{difficulty_path}.coefficient",
        )
        return DifficultyConfig(
            key=difficulty_key,
            name=name,
            coefficient=coefficient,
        )


    def list_difficulties(self) -> list[DifficultyConfig]:
        return [
            self.difficulty(difficulty_key)
            for difficulty_key in self._difficulties
        ]


    def entrance_assessment_snapshot(self) -> dict[str, object]:
        return self._entrance_assessment.snapshot()
