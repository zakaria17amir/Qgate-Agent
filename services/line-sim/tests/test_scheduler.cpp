#define CATCH_CONFIG_MAIN
#include <catch2/catch.hpp>

#include "scheduler.hpp"

using namespace std::chrono_literals;

TEST_CASE("emit offset is sequence times takt, divided by replay speed") {
    CHECK(line_sim::emit_offset(0, 60, 1.0) == 0ms);
    CHECK(line_sim::emit_offset(1, 60, 1.0) == 60000ms);
    CHECK(line_sim::emit_offset(10, 60, 10.0) == 60000ms);
    CHECK(line_sim::emit_offset(3, 45, 2.0) == 67500ms);
}

TEST_CASE("non-positive replay speed is rejected") {
    CHECK_THROWS_AS(line_sim::emit_offset(1, 60, 0.0), std::invalid_argument);
    CHECK_THROWS_AS(line_sim::emit_offset(1, 60, -1.0), std::invalid_argument);
}
