# syntax=docker/dockerfile:1.7
# mock-mes deliberately does NOT depend on qgate-core: it is a foreign system.
ARG PYTHON=3.12.7
FROM ghcr.io/astral-sh/uv:0.4.29-python${PYTHON}-bookworm-slim AS build
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY pyproject.toml uv.lock ./
COPY services/mock-mes/pyproject.toml services/mock-mes/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package qgate-mock-mes
COPY services/mock-mes services/mock-mes
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package qgate-mock-mes

FROM python:${PYTHON}-slim-bookworm AS runtime
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY services/mock-mes/openapi.yaml /workspace/openapi.yaml
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 MES_OPENAPI_PATH=/workspace/openapi.yaml
USER app
EXPOSE 8003
ENTRYPOINT ["mock-mes"]
