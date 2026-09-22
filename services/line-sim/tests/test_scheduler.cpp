#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>

#include "scheduler.hpp"

using namespace std::chrono_literals;

TEST_CASE("emit offset is simulated time since the first event, divided by replay speed") {
    CHECK(line_sim::emit_offset(0, 1.0) == 0ms);
    CHECK(line_sim::emit_offset(60000, 1.0) == 60000ms);
    CHECK(line_sim::emit_offset(600000, 10.0) == 60000ms);
    CHECK(line_sim::emit_offset(135000, 2.0) == 67500ms);
}

TEST_CASE("speed zero means as fast as possible") {
    CHECK(line_sim::emit_offset(0, 0.0) == 0ms);
    CHECK(line_sim::emit_offset(86400000, 0.0) == 0ms);
}

TEST_CASE("negative replay speed is rejected") {
    CHECK_THROWS_AS(line_sim::emit_offset(1, -1.0), std::invalid_argument);
}

TEST_CASE("the schedule is absolute: each due time depends only on its own offset") {
    // Sleeping late for event n must not push event n+1 later (no cumulative drift).
    const auto t0 = std::chrono::steady_clock::time_point{};
    CHECK(line_sim::due_at(t0, 60000, 60000, 1.0) == t0);  // the first event is due at start
    CHECK(line_sim::due_at(t0, 60000, 90000, 1.0) == t0 + 30000ms);
    CHECK(line_sim::due_at(t0, 60000, 180000, 2.0) == t0 + 60000ms);
}
