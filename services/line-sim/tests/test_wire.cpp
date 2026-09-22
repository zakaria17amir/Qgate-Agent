#include <catch2/catch.hpp>

#include "wire.hpp"

TEST_CASE("Confluent wire format: magic byte, big-endian schema id, then the Avro body") {
    const auto framed = line_sim::frame(7, std::string("\x01\x02", 2));
    CHECK(framed == std::string("\x00\x00\x00\x00\x07\x01\x02", 7));
    CHECK(line_sim::frame(0x01020304, "") == std::string("\x00\x01\x02\x03\x04", 5));
}
