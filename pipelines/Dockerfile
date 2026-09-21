# syntax=docker/dockerfile:1.7
ARG PYTHON=3.12.7
FROM ghcr.io/astral-sh/uv:0.4.29-python${PYTHON}-bookworm-slim AS build
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY packages/qgate-core/pyproject.toml packages/qgate-core/
COPY pipelines/pyproject.toml pipelines/
COPY eval/harness/pyproject.toml eval/harness/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package qgate-pipelines --package qgate-eval
COPY packages/qgate-core packages/qgate-core
COPY pipelines pipelines
COPY eval/harness eval/harness
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package qgate-pipelines --package qgate-eval

FROM python:${PYTHON}-slim-bookworm AS runtime
COPY --from=build /opt/venv /opt/venv
COPY --from=build /workspace/pipelines /workspace/pipelines
WORKDIR /workspace/pipelines
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
# runs as root only because it drives the docker socket for replay_scenario; documented in ADR-011 when written
CMD ["prefect", "worker", "start", "--pool", "qgate", "--type", "process"]
