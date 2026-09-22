# syntax=docker/dockerfile:1.7
# Multi-stage: toolchain → build → (test | distroless runtime). Context is the repo root.
# Dependencies come from Debian (no vcpkg): Catch2 v2, nlohmann-json, librdkafka, cpp-httplib.
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build catch2 nlohmann-json3-dev librdkafka-dev libcpp-httplib-dev \
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
