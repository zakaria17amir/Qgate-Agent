"""Measurement-system analysis for an EOL bench: can we trust what it says?

Two independent questions, both in half-tolerance units (tolerance width = 2):

* **Repeatability** (``%GRR``): from repeat readings of the same vehicle, the gauge's own scatter
  as a share of the tolerance band. AIAG MSA convention: ``6 * sigma_gauge / tolerance * 100``,
  acceptable below 30 %.
* **Bias vs peers**: mean deviation this bench reports minus what its sibling benches report
  over the same window. Benches rotate per vehicle, so the populations are comparable; a
  bench that reads 0.9 half-tolerance higher than its peers is failing good cars.

A drifting bench keeps its repeatability and moves its bias, which is why %GRR alone is not the
verdict. Thresholds are stated assumptions; see ``docs/metrology.md``.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

TOLERANCE_WIDTH = 2.0  # half-tolerance units: from -1 to +1
GRR_THRESHOLD_PCT = 30.0  # AIAG: < 10 % good, 10-30 % marginal, > 30 % unacceptable
BIAS_THRESHOLD = 0.5  # half-tolerance units; half the band is an obvious systematic error
MIN_VALUES = 30  # fewer own readings than this and we do not claim anything


@dataclass(frozen=True)
class BenchCapability:
    bench_id: str
    capable: bool
    grr_pct: float | None  # None when no repeat readings exist in the window
    repeatability_sigma: float | None
    bias_vs_peers: float | None  # None when there are no peer readings
    n_repeats: int  # vehicles with >= 2 readings
    n_values: int  # own primary readings in the window
    method: str
    threshold_grr_pct: float = GRR_THRESHOLD_PCT
    threshold_bias: float = BIAS_THRESHOLD


def capability(
    bench_id: str,
    repeats: dict[str, list[float]],
    own: NDArray[np.floating],
    peers: NDArray[np.floating],
) -> BenchCapability:
    """Judge a bench from its repeat readings (per VIN) and its readings versus peer benches."""
    groups = [np.asarray(v) for v in repeats.values() if len(v) >= 2]
    grr = sigma_gauge = None
    if groups:
        # pooled within-vehicle standard deviation: the gauge's scatter with the part held fixed
        ss = sum(float(np.sum((g - g.mean()) ** 2)) for g in groups)
        dof = sum(len(g) - 1 for g in groups)
        sigma_gauge = float(np.sqrt(ss / dof))
        grr = 6 * sigma_gauge / TOLERANCE_WIDTH * 100

    if len(own) < MIN_VALUES:
        return BenchCapability(
            bench_id,
            False,
            grr,
            sigma_gauge,
            None,
            len(groups),
            len(own),
            method="insufficient-data",
        )

    bias = float(np.mean(own) - np.mean(peers)) if len(peers) else None
    repeatable = grr is None or grr < GRR_THRESHOLD_PCT
    unbiased = bias is None or abs(bias) < BIAS_THRESHOLD
    return BenchCapability(
        bench_id,
        repeatable and unbiased,
        grr,
        sigma_gauge,
        bias,
        len(groups),
        len(own),
        method="grr+bias-vs-peers" if grr is not None else "bias-vs-peers",
    )
