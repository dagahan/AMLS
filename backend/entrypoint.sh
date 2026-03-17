#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="src"
CHECK_PATH="${CHECK_PATH:-$PROJECT_ROOT}"

RUFF_RULES="${RUFF_RULES:-ANN,TCH}"
RUFF_IGNORES="${RUFF_IGNORES:-ANN401,TC001,TC003}"
RUFF_FIX="${RUFF_FIX:-0}"

APP_CMD="${APP_CMD:-uv run python main.py}"


if [[ "${RUNNING_INSIDE_DOCKER:-0}" != "1" ]]; then
  echo "📦 Installing dev dependencies (extras)…"
  uv sync --extra dev >/dev/null

  echo "🔎 Ruff (rules: $RUFF_RULES; ignore: ${RUFF_IGNORES:-<none>})…"
  ruff_args=(check "$CHECK_PATH" --select "$RUFF_RULES")
  [[ -n "${RUFF_IGNORES// }" ]] && ruff_args+=(--ignore "$RUFF_IGNORES")
  [[ "$RUFF_FIX" == "1" ]] && ruff_args+=(--fix)
  uv run ruff "${ruff_args[@]}"

  echo "🔬 Mypy (strict)…"
  uv run mypy "$CHECK_PATH"
else
  echo "🐳 RUNNING_INSIDE_DOCKER=1 → skipping Ruff & Mypy."

  if [[ "$APP_CMD" =~ ^[[:space:]]*uv[[:space:]]+run[[:space:]]+ ]]; then
    if [[ ! "$APP_CMD" =~ --no-sync ]]; then
      APP_CMD="${APP_CMD/uv run/uv run --no-sync}"
    fi
  else
    APP_CMD="uv run --no-sync $APP_CMD"
  fi
fi


exec $APP_CMD
