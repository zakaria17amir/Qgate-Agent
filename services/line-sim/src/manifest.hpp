#pragma once

#include <cstdint>
#include <istream>
#include <string>
#include <vector>

namespace line_sim {

// One line of the manifest `qgate-gen export` writes: where it goes, its key, when it happened in
// the scenario, and the schema-less Avro body (ADR-011).
struct Event {
    std::string topic;
    std::string key;
    std::int64_t ts_ms;
    std::string value;
};

std::string from_hex(const std::string& hex);
std::vector<Event> read_manifest(std::istream& in);

}  // namespace line_sim
