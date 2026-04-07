from __future__ import annotations

from typing import Any

from src.config.config_section import ConfigSection


class InfraConfig(ConfigSection):
    __slots__ = ()

    def __init__(self, values: dict[str, Any]) -> None:
        super().__init__(values)


    @property
    def compose_project_name(self) -> str:
        return self._require_string("COMPOSE_PROJECT_NAME")


    @property
    def running_inside_docker(self) -> bool:
        return self._require_flag("RUNNING_INSIDE_DOCKER")


    @property
    def time_zone_name(self) -> str:
        return self._require_string("TZ")


    @property
    def log_level_name(self) -> str:
        return self._require_string("LOG_LEVEL")


    @property
    def log_renderer_name(self) -> str:
        return self._require_string("LOG_RENDERER")


    @property
    def access_logs_enabled(self) -> bool:
        return self._require_flag("LOG_ACCESS_LOGS")


    @property
    def backend_host(self) -> str:
        return self._require_string("BACKEND_HOST")


    @property
    def backend_port(self) -> int:
        return self._require_integer("BACKEND_PORT")


    @property
    def postgres_host(self) -> str:
        return self._require_string("POSTGRES_HOST")


    @property
    def postgres_port(self) -> int:
        return self._require_integer("POSTGRES_PORT")


    @property
    def postgres_user(self) -> str:
        return self._require_string("POSTGRES_USER")


    @property
    def postgres_password(self) -> str:
        return self._require_string("POSTGRES_PASSWORD")


    @property
    def postgres_database_name(self) -> str:
        return self._require_string("POSTGRES_DB")


    @property
    def valkey_host(self) -> str:
        return self._require_string("VALKEY_HOST")


    @property
    def valkey_port(self) -> int:
        return self._require_integer("VALKEY_PORT")


    @property
    def access_token_expire_minutes(self) -> int:
        return self._require_integer("ACCESS_TOKEN_EXPIRE_MINUTES")


    @property
    def refresh_token_expire_days(self) -> int:
        return self._require_integer("REFRESH_TOKEN_EXPIRE_DAYS")


    @property
    def sessions_max_life_days(self) -> int:
        return self._require_integer("SESSIONS_MAX_LIFE_DAYS")


    @property
    def sessions_inactive_days(self) -> int:
        return self._require_integer("SESSIONS_INACTIVE_DAYS")


    @property
    def jwt_private_key_path(self) -> str:
        return self._require_string("JWT_PRIVATE_KEY_PATH")


    @property
    def jwt_public_key_path(self) -> str:
        return self._require_string("JWT_PUBLIC_KEY_PATH")


    @property
    def database_echo(self) -> bool:
        return self._require_flag("DB_ECHO")


    @property
    def database_pool_size(self) -> int:
        return self._require_integer("DB_POOL_SIZE")


    @property
    def database_max_overflow(self) -> int:
        return self._require_integer("DB_MAX_OVERFLOW")


    @property
    def s3_bucket_name(self) -> str:
        return self._require_string("S3_BUCKET_NAME")


    @property
    def s3_endpoint_url(self) -> str:
        return self._require_string("S3_ENDPOINT_URL")


    @property
    def s3_access_key(self) -> str:
        return self._require_string("S3_ACCESS_KEY")


    @property
    def s3_secret_key(self) -> str:
        return self._require_string("S3_SECRET_KEY")


    @property
    def s3_region(self) -> str:
        return self._require_string("S3_REGION")


    @property
    def s3_tls_verify(self) -> bool:
        return self._require_flag("S3_TLS_VERIFY")


    @property
    def node_binary(self) -> str:
        return self._require_string("NODE_BINARY")


    @property
    def lms_base_url(self) -> str:
        raw_value = self._values.get("LMS_BASE_URL")
        if not isinstance(raw_value, str) or raw_value.strip() == "":
            return "http://nikiausovs-macbook-pro.tail89767d.ts.net:1234/v1"
        return raw_value


    @property
    def lms_api_key(self) -> str:
        raw_value = self._values.get("LMS_API_KEY")
        if not isinstance(raw_value, str) or raw_value.strip() == "":
            return "lm-studio"
        return raw_value


    @property
    def lms_model(self) -> str:
        raw_value = self._values.get("LMS_MODEL")
        if not isinstance(raw_value, str) or raw_value.strip() == "":
            return "qwen2.5-coder-3b-instruct-mlx"
        return raw_value


    @property
    def lms_timeout_seconds(self) -> int:
        raw_value = self._values.get("LMS_TIMEOUT_SECONDS")
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return raw_value
        return 30


    @property
    def lms_auto_wake_enabled(self) -> bool:
        raw_value = self._values.get("LMS_AUTO_WAKE_ENABLED")
        if isinstance(raw_value, bool):
            return raw_value
        if isinstance(raw_value, int):
            return raw_value == 1
        return True


    @property
    def lms_auto_wake_timeout_seconds(self) -> int:
        raw_value = self._values.get("LMS_AUTO_WAKE_TIMEOUT_SECONDS")
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return max(1, raw_value)
        return 15


    @property
    def lms_auto_wake_retry_count(self) -> int:
        raw_value = self._values.get("LMS_AUTO_WAKE_RETRY_COUNT")
        if isinstance(raw_value, int) and not isinstance(raw_value, bool):
            return max(0, raw_value)
        return 2
