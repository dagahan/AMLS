import hashlib
import os
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
from dotenv import find_dotenv, load_dotenv
from loguru import logger


class FileSystemTools:
    @staticmethod
    def ensure_directory_exists(directory: str) -> None:
        Path(directory).mkdir(parents=True, exist_ok=True)


class EnvTools:
    @staticmethod
    def _find_project_root(markers: Iterable[str] = (".env", "docker-compose.yml")) -> Path:
        current_path = Path.cwd().resolve()
        visited_paths: set[Path] = set()

        while True:
            if any((current_path / marker).exists() for marker in markers):
                return current_path

            if current_path in visited_paths or current_path.parent == current_path:
                return Path.cwd().resolve()

            visited_paths.add(current_path)
            current_path = current_path.parent


    @staticmethod
    def _load_variables_from_file(path: Path, override: bool) -> None:
        if path.exists():
            load_dotenv(path, override=override, interpolate=True, encoding="utf-8")


    @staticmethod
    def get_project_root() -> Path:
        return EnvTools._find_project_root()


    @staticmethod
    def resolve_project_path(path_value: str) -> Path:
        path = Path(path_value)
        if path.is_absolute():
            return path
        return EnvTools.get_project_root() / path


    @staticmethod
    def bootstrap_env() -> None:
        if os.getenv("RUNNING_INSIDE_DOCKER") == "1":
            return

        project_root = EnvTools.get_project_root()
        EnvTools._load_variables_from_file(project_root / ".env", override=True)

        os.environ.setdefault("RUNNING_INSIDE_DOCKER", "0")


    @staticmethod
    def load_env_var(variable_name: str) -> str | None:
        dotenv_path = find_dotenv(usecwd=True)
        if dotenv_path:
            load_dotenv(dotenv_path=dotenv_path)
        return os.getenv(variable_name)


    @staticmethod
    def required_load_env_var(variable_name: str) -> str:
        value = EnvTools.load_env_var(variable_name)
        if value is None or value == "":
            raise RuntimeError(f"Missing required environment variable: {variable_name}")
        return value


    @staticmethod
    def set_env_var(variable_name: str, variable_value: str) -> None:
        os.environ[variable_name] = variable_value


    @staticmethod
    def is_running_inside_docker_compose() -> bool:
        return EnvTools.load_env_var("RUNNING_INSIDE_DOCKER") == "1"


    @staticmethod
    def get_service_host(service_name: str) -> str:
        if EnvTools.is_running_inside_docker_compose():
            project_name = EnvTools.required_load_env_var("COMPOSE_PROJECT_NAME")
            return f"{service_name}-{project_name}"
        return EnvTools.required_load_env_var(f"{service_name.upper()}_HOST")


    @staticmethod
    def get_service_port(service_name: str) -> str:
        return EnvTools.required_load_env_var(f"{service_name.upper()}_PORT")


class StringTools:
    @staticmethod
    def hash_string(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PasswordTools:
    @staticmethod
    def hash_password(value: str) -> str:
        return bcrypt.hashpw(value.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


    @staticmethod
    def verify_password(plain_value: str, hashed_value: str) -> bool:
        try:
            return bcrypt.checkpw(plain_value.encode("utf-8"), hashed_value.encode("utf-8"))
        except ValueError as error:
            logger.error(f"Password verification failed: {error}")
            return False


class TimeTools:
    @staticmethod
    def now_time_zone() -> datetime:
        time_zone_name = EnvTools.load_env_var("TZ") or "UTC"
        try:
            time_zone = ZoneInfo(time_zone_name)
        except Exception:
            time_zone = ZoneInfo("UTC")
        return datetime.now(time_zone)


    @staticmethod
    def now_time_stamp() -> int:
        return int(TimeTools.now_time_zone().timestamp())
