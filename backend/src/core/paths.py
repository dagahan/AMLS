from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def find_project_root(markers: Iterable[str] = (".env", "docker-compose.yml")) -> Path:
    current_path = Path.cwd().resolve()
    visited_paths: set[Path] = set()

    while True:
        if any((current_path / marker).exists() for marker in markers):
            return current_path

        if current_path in visited_paths or current_path.parent == current_path:
            return Path.cwd().resolve()

        visited_paths.add(current_path)
        current_path = current_path.parent


def resolve_project_path(path_value: str, project_root: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (project_root or find_project_root()) / path
