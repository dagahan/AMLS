from __future__ import annotations

from collections import defaultdict


def build_problem_type_tree_lines(
    problem_type_data: tuple[tuple[str, str | None], ...],
) -> tuple[str, ...]:
    child_names_by_parent: dict[str, list[str]] = defaultdict(list)
    root_names: list[str] = []
    seen_problem_type_names: set[str] = set()

    for problem_type_name, prerequisite_name in problem_type_data:
        if problem_type_name in seen_problem_type_names:
            continue
        seen_problem_type_names.add(problem_type_name)

        if prerequisite_name is None:
            root_names.append(problem_type_name)
            continue

        child_names_by_parent[prerequisite_name].append(problem_type_name)

    lines: list[str] = []
    for root_name in root_names:
        _append_problem_type_tree_lines(
            problem_type_name=root_name,
            child_names_by_parent=child_names_by_parent,
            indent_level=0,
            lines=lines,
        )

    return tuple(lines)


def build_problem_type_tree_text(
    problem_type_data: tuple[tuple[str, str | None], ...],
) -> str:
    return "\n".join(build_problem_type_tree_lines(problem_type_data))


def _append_problem_type_tree_lines(
    problem_type_name: str,
    child_names_by_parent: dict[str, list[str]],
    indent_level: int,
    lines: list[str],
) -> None:
    lines.append(("  " * indent_level) + problem_type_name)

    for child_name in child_names_by_parent.get(problem_type_name, []):
        _append_problem_type_tree_lines(
            problem_type_name=child_name,
            child_names_by_parent=child_names_by_parent,
            indent_level=indent_level + 1,
            lines=lines,
        )
