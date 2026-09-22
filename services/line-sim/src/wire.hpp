#pragma once

#include <cstdint>
#include <string>

namespace line_sim {

// Confluent Schema Registry wire format: 0x00, the schema id as 4 big-endian bytes, the Avro body.
inline std::string frame(std::uint32_t schema_id, const std::string& avro) {
    std::string out;
    out.reserve(5 + avro.size());
    out.push_back('\0');
    for (int shift = 24; shift >= 0; shift -= 8)
        out.push_back(static_cast<char>((schema_id >> shift) & 0xff));
    out += avro;
    return out;
}

}  // namespace line_sim
