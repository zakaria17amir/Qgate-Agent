"""Statistical process control on standardised deviations.

Inputs are z-scores: ``(value - nominal) / sigma`` where sigma is the process standard deviation
for that characteristic. Classic Western Electric rules (1956) plus an EWMA chart for small,
sustained shifts that the run rules miss.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Floats = NDArray[np.floating]


@dataclass(frozen=True)
class Violation:
    rule: int  # Western Electric rule number, 1..4
    index: int  # position in the series where the rule fired


def western_electric(z: Floats) -> list[Violation]:
    """Return every rule violation, reporting the index at which the pattern completed.

    1. one point beyond 3 sigma
    2. two of three consecutive beyond 2 sigma, same side
    3. four of five consecutive beyond 1 sigma, same side
    4. eight consecutive on the same side of centre
    """
    hits: list[Violation] = []
    n = len(z)
    for i in range(n):
        if abs(z[i]) > 3:
            hits.append(Violation(1, i))
        if i >= 2 and _same_side_count(z[i - 2 : i + 1], 2) >= 2:
            hits.append(Violation(2, i))
        if i >= 4 and _same_side_count(z[i - 4 : i + 1], 1) >= 4:
            hits.append(Violation(3, i))
        if i >= 7 and (np.all(z[i - 7 : i + 1] > 0) or np.all(z[i - 7 : i + 1] < 0)):
            hits.append(Violation(4, i))
    return hits


def _same_side_count(window: Floats, k: float) -> int:
    """Largest count of points beyond ``k`` sigma on one side of centre within ``window``."""
    return int(max(np.sum(window > k), np.sum(window < -k)))


def ewma_breaches(z: Floats, lam: float = 0.2, limit: float = 3.0) -> NDArray[np.bool_]:
    """EWMA chart: True where the smoothed statistic leaves its control limits.

    ``lam`` = 0.2 weights recent points; the steady-state limit is
    ``limit * sqrt(lam / (2 - lam))`` in sigma units. Small sustained shifts (~1 sigma) that never
    trip a single-point rule accumulate here within a dozen points.
    """
    s = np.empty_like(z, dtype=float)
    acc = 0.0
    for i, v in enumerate(z):
        acc = lam * v + (1 - lam) * acc
        s[i] = acc
    bound = limit * np.sqrt(lam / (2 - lam))
    return np.asarray(np.abs(s) > bound)
