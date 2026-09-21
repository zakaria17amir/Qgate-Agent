# syntax=docker/dockerfile:1.7
# One image recipe for every Python workspace member. Context is the repo root.
#   docker build -f docker/python.Dockerfile --build-arg PACKAGE=qgate-api --build-arg ENTRYPOINT=api .
ARG PYTHON=3.12
FROM ghcr.io/astral-sh/uv:python${PYTHON}-bookworm-slim AS build
ARG PACKAGE
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package "${PACKAGE}"

FROM python:${PYTHON}-slim-bookworm AS runtime
ARG ENTRYPOINT
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /workspace/db/queries /workspace/db/queries
COPY --from=build /workspace/services/mock-mes/openapi.yaml /workspace/openapi.yaml
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    QGATE_QUERIES_DIR=/workspace/db/queries MES_OPENAPI_PATH=/workspace/openapi.yaml \
    ENTRYPOINT="${ENTRYPOINT}"
USER app
ENTRYPOINT ["/bin/sh", "-c", "exec \"$ENTRYPOINT\" \"$@\"", "--"]
