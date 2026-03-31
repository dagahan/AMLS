from __future__ import annotations

from pathlib import Path

from src.config.business_config import BusinessConfig, DifficultyConfig
from src.config.infra_config import InfraConfig


class AppConfig:
    __slots__ = ("business", "business_hash", "infra", "project_root")

    def __init__(
        self,
        *,
        project_root: Path,
        infra: InfraConfig,
        business: BusinessConfig,
        business_hash: str,
    ) -> None:
        self.project_root = project_root
        self.infra = infra
        self.business = business
        self.business_hash = business_hash


    def backend_bind_host(self) -> str:
        if self.infra.running_inside_docker:
            return "0.0.0.0"
        return self.infra.backend_host


    def postgres_host(self) -> str:
        if self.infra.running_inside_docker:
            return self._docker_service_host("postgres")
        return self.infra.postgres_host


    def valkey_host(self) -> str:
        if self.infra.running_inside_docker:
            return self._docker_service_host("valkey")
        return self.infra.valkey_host


    def resolve_path(self, path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return self.project_root / path


    def difficulty(self, difficulty_key: str) -> DifficultyConfig:
        return self.business.difficulty(difficulty_key)


    def list_difficulties(self) -> list[DifficultyConfig]:
        return self.business.list_difficulties()


    def entrance_assessment_snapshot(self) -> dict[str, object]:
        return self.business.entrance_assessment_snapshot()


    def _docker_service_host(self, service_name: str) -> str:
        return f"{service_name}-{self.infra.compose_project_name}"
