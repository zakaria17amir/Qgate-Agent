# syntax=docker/dockerfile:1.7
# Multi-stage: toolchain → build → (test | distroless runtime). Context is the repo root.
# Dependencies come from Debian (no vcpkg): Catch2 v2, nlohmann-json, librdkafka, cpp-httplib.
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build pkg-config catch2 nlohmann-json3-dev librdkafka-dev libcpp-httplib-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY services/line-sim .
RUN cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DLINE_SIM_BUILD_TESTS=ON \
    && cmake --build build

FROM build AS test
CMD ["ctest", "--test-dir", "build", "--output-on-failure"]

# Runtime: slim Debian rather than distroless so librdkafka's shared library (and its TLS/SASL
# dependencies) come from apt instead of being hand-copied. Non-root, nothing else installed.
FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends librdkafka1 libcpp-httplib0.11 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin linesim
COPY --from=build /src/build/line-sim /usr/local/bin/line-sim
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/line-sim"]
