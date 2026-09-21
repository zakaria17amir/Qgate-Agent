cmake_minimum_required(VERSION 3.25)
project(line_sim VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

option(LINE_SIM_BUILD_TESTS "Build Catch2 tests" ON)

# Core library: everything except main(), so tests link against it.
add_library(line_sim_core src/scheduler.cpp)
target_include_directories(line_sim_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_options(line_sim_core PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(line-sim src/main.cpp)
target_link_libraries(line-sim PRIVATE line_sim_core)

if(LINE_SIM_BUILD_TESTS)
    enable_testing()
    find_package(Catch2 2 CONFIG REQUIRED)   # Debian bookworm ships Catch2 2.13
    add_executable(line_sim_tests tests/test_scheduler.cpp)
    target_link_libraries(line_sim_tests PRIVATE line_sim_core Catch2::Catch2)
    include(Catch)
    catch_discover_tests(line_sim_tests)
endif()

install(TARGETS line-sim RUNTIME DESTINATION bin)
