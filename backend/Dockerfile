FROM debian:12-slim


RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates tzdata libgomp1 libstdc++6 libgcc-s1 libffi8 openssl libsqlite3-0 \
  && update-ca-certificates \
  && rm -rf /var/lib/apt/lists/*


RUN useradd -m -s /bin/bash appuser && \
    mkdir -p /app/gen && \
    mkdir -p /app /data/models && \
    chown -R appuser:appuser /app /data


RUN curl -fsSL https://astral.sh/uv/install.sh -o /tmp/uv-installer.sh
RUN sh /tmp/uv-installer.sh ~/.local/bin \
    && rm /tmp/uv-installer.sh


RUN mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx \
    && chmod +x /usr/local/bin/uv /usr/local/bin/uvx
ENV PATH="/usr/local/bin:${PATH}"


ENV UV_PYTHON_PREFERENCE=managed \
    UV_PYTHON_DOWNLOADS=auto \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1


WORKDIR /app


COPY --chown=appuser:appuser pyproject.toml uv.lock* ./


USER appuser


RUN set -eux; \
    REQ="$(sed -nE 's/^[[:space:]]*requires-python[[:space:]]*=\s*"==?([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' pyproject.toml | head -n1)"; \
    echo "uv: installing CPython ${REQ} (managed)…"; \
    uv python install "${REQ}"; \
    uv sync --no-dev


COPY --chown=appuser:appuser . /app
RUN chmod +x /app/entrypoint.sh


ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:${PATH}"


EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]

