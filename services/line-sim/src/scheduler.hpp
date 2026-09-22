#pragma once

#include <chrono>
#include <cstdint>

namespace line_sim {

inline constexpr const char* kVersion = "0.2.0";

// How long after replay start an event stamped `sim_ms_since_first` ms into the scenario is due,
// compressed by `speed` (10.0 = ten times faster than the line; 0 = as fast as possible).
std::chrono::milliseconds emit_offset(std::int64_t sim_ms_since_first, double speed);

// Absolute due time. Computed from `start` every time, never from "now + delta", so a late event
// does not push the ones after it: the schedule cannot drift.
std::chrono::steady_clock::time_point due_at(std::chrono::steady_clock::time_point start,
                                             std::int64_t first_ts_ms, std::int64_t ts_ms,
                                             double speed);

}  // namespace line_sim
