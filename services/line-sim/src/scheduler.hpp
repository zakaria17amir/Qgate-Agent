#pragma once

#include <chrono>
#include <cstdint>

namespace line_sim {

inline constexpr const char* kVersion = "0.1.0";

// Wall-clock offset from replay start at which vehicle `sequence_no` is emitted:
// one vehicle per takt, compressed by `speed` (10.0 = ten times faster than the line).
std::chrono::milliseconds emit_offset(std::int64_t sequence_no, int takt_s, double speed);

}  // namespace line_sim
