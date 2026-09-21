cmake_minimum_required(VERSION 3.25)
project(line_sim VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(LINE_SIM_BUILD_TESTS "Build Catch2 tests" ON)

find_package(RdKafka CONFIG REQUIRED)     # vcpkg: librdkafka
find_package(nlohmann_json CONFIG REQUIRED)
find_package(yaml-cpp CONFIG REQUIRED)
find_package(spdlog CONFIG REQUIRED)
find_package(CLI11 CONFIG REQUIRED)

# Core library: everything except main(), so tests link against it.
add_library(line_sim_core
    src/scheduler.cpp
    src/producer.cpp
    src/scenario_reader.cpp
)
target_include_directories(line_sim_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(line_sim_core PUBLIC
    RdKafka::rdkafka++
    nlohmann_json::nlohmann_json
    yaml-cpp::yaml-cpp
    spdlog::spdlog
)
target_compile_options(line_sim_core PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(line-sim src/main.cpp)
target_link_libraries(line-sim PRIVATE line_sim_core CLI11::CLI11)

if(LINE_SIM_BUILD_TESTS)
    enable_testing()
    find_package(Catch2 3 CONFIG REQUIRED)
    add_executable(line_sim_tests
        tests/test_scheduler.cpp
        tests/test_scenario_reader.cpp
    )
    target_link_libraries(line_sim_tests PRIVATE line_sim_core Catch2::Catch2WithMain)
    include(Catch)
    catch_discover_tests(line_sim_tests)
endif()

install(TARGETS line-sim RUNTIME DESTINATION bin)
