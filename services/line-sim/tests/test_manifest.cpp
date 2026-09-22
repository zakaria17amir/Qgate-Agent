#include <catch2/catch.hpp>
#include <sstream>

#include "manifest.hpp"

TEST_CASE("a manifest line becomes an event with decoded bytes") {
    std::istringstream in(
        R"({"topic":"line.build.events","key":"SYN1","ts_ms":1767592800000,"avro_hex":"0a53542d3031"})"
        "\n"
        R"({"topic":"line.measurements","key":"SYN1","ts_ms":1767592801000,"avro_hex":"00ff"})"
        "\n");
    const auto events = line_sim::read_manifest(in);
    REQUIRE(events.size() == 2);
    CHECK(events[0].topic == "line.build.events");
    CHECK(events[0].key == "SYN1");
    CHECK(events[0].ts_ms == 1767592800000);
    CHECK(events[0].value == std::string("\x0aST-01", 6));
    CHECK(events[1].value == std::string("\x00\xff", 2));
}

TEST_CASE("blank lines are skipped") {
    std::istringstream in("\n{\"topic\":\"t\",\"key\":\"k\",\"ts_ms\":1,\"avro_hex\":\"\"}\n\n");
    CHECK(line_sim::read_manifest(in).size() == 1);
}

TEST_CASE("a malformed line names its line number") {
    std::istringstream in(
        "{\"topic\":\"t\",\"key\":\"k\",\"ts_ms\":1,\"avro_hex\":\"00\"}\n{\"topic\":\"t\",\"key\":"
        "\"k\",\"ts_ms\":2,\"avro_hex\":\"abc\"}\n");
    CHECK_THROWS_WITH(line_sim::read_manifest(in), Catch::Contains("line 2"));
}

TEST_CASE("hex decoding") {
    CHECK(line_sim::from_hex("") == "");
    CHECK(line_sim::from_hex("00ff7A") == std::string("\x00\xff\x7a", 3));
    CHECK_THROWS_AS(line_sim::from_hex("0"), std::invalid_argument);
    CHECK_THROWS_AS(line_sim::from_hex("zz"), std::invalid_argument);
}
