# syntax=docker/dockerfile:1.7
# Multi-stage: toolchain → build → (test | distroless runtime). Context is the repo root.
# Dependencies come from Debian; Phase 4 adds librdkafka-dev, nlohmann-json3-dev, libyaml-cpp-dev here.
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build catch2 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY services/line-sim .
RUN cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DLINE_SIM_BUILD_TESTS=ON \
    && cmake --build build

FROM build AS test
CMD ["ctest", "--test-dir", "build", "--output-on-failure"]

FROM gcr.io/distroless/cc-debian12:nonroot AS runtime
COPY --from=build /src/build/line-sim /usr/local/bin/line-sim
ENTRYPOINT ["/usr/local/bin/line-sim"]
