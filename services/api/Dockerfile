# syntax=docker/dockerfile:1.7
ARG PYTHON=3.12.7
FROM ghcr.io/astral-sh/uv:0.4.29-python${PYTHON}-bookworm-slim AS build
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY packages/qgate-core/pyproject.toml packages/qgate-core/
COPY services/api/pyproject.toml services/api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package qgate-api
COPY packages/qgate-core packages/qgate-core
COPY services/api services/api
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package qgate-api

FROM python:${PYTHON}-slim-bookworm AS runtime
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
ENTRYPOINT ["api"]
