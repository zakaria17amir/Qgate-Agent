# syntax=docker/dockerfile:1.7
ARG PYTHON=3.12.7
FROM ghcr.io/astral-sh/uv:0.4.29-python${PYTHON}-bookworm-slim AS build
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY packages/qgate-core/pyproject.toml packages/qgate-core/
COPY services/agent/pyproject.toml services/agent/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package qgate-agent
COPY packages/qgate-core packages/qgate-core
COPY services/agent services/agent
COPY db/queries db/queries
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package qgate-agent

FROM python:${PYTHON}-slim-bookworm AS runtime
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /workspace/db/queries /workspace/db/queries
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 QGATE_QUERIES_DIR=/workspace/db/queries
USER app
EXPOSE 8001
ENTRYPOINT ["agent"]
