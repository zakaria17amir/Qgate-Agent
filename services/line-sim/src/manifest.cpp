#include "manifest.hpp"

#include <nlohmann/json.hpp>
#include <stdexcept>

namespace line_sim {

std::string from_hex(const std::string& hex) {
    if (hex.size() % 2 != 0) throw std::invalid_argument("odd-length hex");
    auto nibble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        throw std::invalid_argument("not a hex digit");
    };
    std::string out;
    out.reserve(hex.size() / 2);
    for (std::size_t i = 0; i < hex.size(); i += 2)
        out.push_back(static_cast<char>(nibble(hex[i]) * 16 + nibble(hex[i + 1])));
    return out;
}

std::vector<Event> read_manifest(std::istream& in) {
    std::vector<Event> events;
    std::string line;
    for (std::size_t n = 1; std::getline(in, line); ++n) {
        if (line.empty()) continue;
        try {
            const auto j = nlohmann::json::parse(line);
            events.push_back({j.at("topic").get<std::string>(), j.at("key").get<std::string>(),
                              j.at("ts_ms").get<std::int64_t>(),
                              from_hex(j.at("avro_hex").get<std::string>())});
        } catch (const std::exception& e) {
            throw std::runtime_error("manifest line " + std::to_string(n) + ": " + e.what());
        }
    }
    return events;
}

}  // namespace line_sim
