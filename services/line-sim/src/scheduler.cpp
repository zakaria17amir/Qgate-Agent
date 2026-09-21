#include "scheduler.hpp"

#include <stdexcept>

namespace line_sim {

std::chrono::milliseconds emit_offset(std::int64_t sequence_no, int takt_s, double speed) {
    if (speed <= 0.0) throw std::invalid_argument("replay speed must be positive");
    const double ms = static_cast<double>(sequence_no) * takt_s * 1000.0 / speed;
    return std::chrono::milliseconds{static_cast<std::int64_t>(ms)};
}

}  // namespace line_sim
