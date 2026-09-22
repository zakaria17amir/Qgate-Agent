#include "scheduler.hpp"

#include <stdexcept>

namespace line_sim {

std::chrono::milliseconds emit_offset(std::int64_t sim_ms_since_first, double speed) {
    if (speed < 0.0) throw std::invalid_argument("replay speed must not be negative");
    if (speed == 0.0) return std::chrono::milliseconds{0};
    return std::chrono::milliseconds{
        static_cast<std::int64_t>(static_cast<double>(sim_ms_since_first) / speed)};
}

std::chrono::steady_clock::time_point due_at(std::chrono::steady_clock::time_point start,
                                             std::int64_t first_ts_ms, std::int64_t ts_ms,
                                             double speed) {
    return start + emit_offset(ts_ms - first_ts_ms, speed);
}

}  // namespace line_sim
