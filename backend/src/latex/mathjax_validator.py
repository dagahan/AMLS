from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.config import get_app_config
from src.models.pydantic.problem import ProblemAnswerOptionPayload


class LatexValidationError(Exception):
    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        self.message = message
        super().__init__(f"Invalid LaTeX in {field_name}: {message}")


class MathJaxValidator:
    def __init__(self) -> None:
        app_config = get_app_config()
        self.node_binary = app_config.infra.node_binary
        self.script_path = app_config.resolve_path(
            "backend/src/latex/validate_latex.mjs"
        )


    async def validate_problem_content(
        self,
        condition: str | None = None,
        solution: str | None = None,
        answer_options: list[ProblemAnswerOptionPayload] | None = None,
    ) -> None:
        entries: list[dict[str, object]] = []

        if condition is not None:
            entries.append(self._build_entry("condition", condition, True))

        if solution is not None:
            entries.append(self._build_entry("solution", solution, True))

        if answer_options is not None:
            for index, answer_option in enumerate(answer_options):
                entries.append(
                    self._build_entry(
                        f"answer_options[{index}]",
                        answer_option.text,
                        False,
                    )
                )

        if not entries:
            return

        payload = json.dumps({"entries": entries}, ensure_ascii=False).encode("utf-8")
        process = await asyncio.create_subprocess_exec(
            self.node_binary,
            str(self._resolve_script_path()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(payload)

        if process.returncode != 0:
            error_output = stderr.decode("utf-8").strip() or stdout.decode("utf-8").strip()
            raise RuntimeError(f"MathJax validation failed: {error_output}")

        raw_result = stdout.decode("utf-8").strip()
        result = json.loads(raw_result)
        if not bool(result.get("ok")):
            field_name = str(result.get("field_name", "unknown"))
            message = str(result.get("message", "MathJax validation failed"))
            raise LatexValidationError(field_name, message)


    def _resolve_script_path(self) -> Path:
        if not self.script_path.exists():
            raise RuntimeError(f"MathJax validation script not found: {self.script_path}")
        return self.script_path


    def _build_entry(self, field_name: str, value: str, display: bool) -> dict[str, object]:
        return {
            "field_name": field_name,
            "value": value,
            "display": display,
        }
