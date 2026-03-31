from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from src.config.manager import ConfigManager


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


def test_config_manager_builds_typed_snapshot(tmp_path: Path) -> None:
    project_root = _create_project_copy(tmp_path)

    app_config = ConfigManager(project_root=project_root).bootstrap()

    assert app_config.infra.backend_port == 8000
    assert app_config.infra.time_zone_name == "UTC"
    assert app_config.difficulty("elementary").name == "Elementary"
    assert app_config.resolve_path("backend/certs/jwt-private.pem") == (
        project_root / "backend/certs/jwt-private.pem"
    )


def test_config_manager_accepts_new_unmapped_config_values(tmp_path: Path) -> None:
    project_root = _create_project_copy(tmp_path)
    env_path = project_root / ".env"
    settings_path = project_root / "config/settings.toml"

    _append_text(env_path, '\nEXPERIMENTAL_FLAG="enabled"\n')
    _append_text(
        settings_path,
        "\n[adaptive_thresholds]\nminimum_probability = 0.61\n",
    )

    app_config = ConfigManager(project_root=project_root).bootstrap()

    assert app_config.infra.backend_port == 8000
    assert app_config.difficulty("elementary").coefficient == 0.5


def test_config_manager_uses_env_file_as_source_of_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _create_project_copy(tmp_path)
    env_path = project_root / ".env"

    _replace_first(env_path, "BACKEND_PORT=8000", "BACKEND_PORT=8011")
    monkeypatch.setenv("BACKEND_PORT", "9999")

    app_config = ConfigManager(project_root=project_root).bootstrap()

    assert app_config.infra.backend_port == 8011


@pytest.mark.asyncio
async def test_business_config_watcher_hot_reloads(tmp_path: Path) -> None:
    project_root = _create_project_copy(tmp_path)
    settings_path = project_root / "config/settings.toml"
    manager = ConfigManager(project_root=project_root)
    initial_config = manager.bootstrap()

    await manager.start_watcher(interval_seconds=0.01)

    try:
        _replace_first(settings_path, "coefficient = 0.5", "coefficient = 0.55")

        for _ in range(50):
            if manager.app_config.difficulty("elementary").coefficient == 0.55:
                break
            await asyncio.sleep(0.02)
    finally:
        await manager.stop_watcher()

    assert manager.app_config.difficulty("elementary").coefficient == 0.55
    assert manager.app_config.business_hash != initial_config.business_hash


@pytest.mark.asyncio
async def test_reload_business_config_keeps_previous_snapshot_on_validation_error(
    tmp_path: Path,
) -> None:
    project_root = _create_project_copy(tmp_path)
    settings_path = project_root / "config/settings.toml"
    manager = ConfigManager(project_root=project_root)
    initial_config = manager.bootstrap()

    _replace_first(settings_path, "coefficient = 0.5", "coefficient = -1.0")

    with pytest.raises(RuntimeError):
        await manager.reload_business_config()

    assert manager.app_config.business_hash == initial_config.business_hash
    assert manager.app_config.difficulty("elementary").coefficient == 0.5


def _create_project_copy(tmp_path: Path) -> Path:
    project_root = tmp_path / "amls-project"
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True)

    shutil.copy2(PROJECT_ROOT / ".env", project_root / ".env")
    shutil.copy2(PROJECT_ROOT / "config/settings.toml", config_dir / "settings.toml")
    shutil.copy2(
        PROJECT_ROOT / "config/dynaconf_validators.toml",
        config_dir / "dynaconf_validators.toml",
    )

    return project_root


def _replace_first(path: Path, old_value: str, new_value: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated_content = content.replace(old_value, new_value, 1)
    path.write_text(updated_content, encoding="utf-8")


def _append_text(path: Path, content: str) -> None:
    current_content = path.read_text(encoding="utf-8")
    path.write_text(f"{current_content}{content}", encoding="utf-8")
