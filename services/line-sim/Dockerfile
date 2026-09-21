# syntax=docker/dockerfile:1.7
# Multi-stage: vcpkg deps → build → (test | distroless runtime). Context is the repo root.
FROM debian:bookworm-slim AS toolchain
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git curl zip unzip tar pkg-config ca-certificates \
        clang-format \
    && rm -rf /var/lib/apt/lists/*
ENV VCPKG_ROOT=/opt/vcpkg VCPKG_FORCE_SYSTEM_BINARIES=1
RUN git clone --depth 1 https://github.com/microsoft/vcpkg.git $VCPKG_ROOT \
    && $VCPKG_ROOT/bootstrap-vcpkg.sh -disableMetrics

FROM toolchain AS deps
WORKDIR /src
COPY services/line-sim/vcpkg.json .
RUN --mount=type=cache,target=/root/.cache/vcpkg \
    $VCPKG_ROOT/vcpkg install --triplet x64-linux

FROM deps AS build
COPY services/line-sim .
RUN cmake -S . -B build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE=$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake \
        -DLINE_SIM_BUILD_TESTS=ON \
    && cmake --build build

FROM build AS test
CMD ["ctest", "--test-dir", "build", "--output-on-failure"]

FROM gcr.io/distroless/cc-debian12:nonroot AS runtime
COPY --from=build /src/build/line-sim /usr/local/bin/line-sim
ENTRYPOINT ["/usr/local/bin/line-sim"]
