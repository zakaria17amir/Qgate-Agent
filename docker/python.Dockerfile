# syntax=docker/dockerfile:1.7
# One image recipe for every Python workspace member. Context is the repo root.
#   docker build -f docker/python.Dockerfile --build-arg PACKAGE=qgate-api --build-arg ENTRYPOINT=api .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim@sha256:e5b65587bce7de595f299855d7385fe7fca39b8a74baa261ba1b7147afa78e58 AS build
ARG PACKAGE
WORKDIR /workspace
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package "${PACKAGE}"

FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime
ARG ENTRYPOINT
# /data pre-owned by app: a fresh named volume mounted there inherits the ownership (gen writes manifests)
RUN groupadd -g 10001 app && useradd -u 10001 -g app -M -s /usr/sbin/nologin app \
    && mkdir /data && chown app:app /data
COPY --from=build /opt/venv /opt/venv
COPY --from=build /workspace/db /workspace/db
COPY --from=build /workspace/services/mock-mes/openapi.yaml /workspace/openapi.yaml
COPY --from=build /workspace/pipelines /workspace/pipelines
COPY --from=build /workspace/eval/goldens /workspace/eval/goldens
COPY --from=build /workspace/scenarios /workspace/scenarios
COPY --from=build /workspace/knowledge /workspace/knowledge
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 \
    QGATE_QUERIES_DIR=/workspace/db/queries MES_OPENAPI_PATH=/workspace/openapi.yaml \
    ENTRYPOINT="${ENTRYPOINT}"
USER app
ENTRYPOINT ["/bin/sh", "-c", "exec \"$ENTRYPOINT\" \"$@\"", "--"]
