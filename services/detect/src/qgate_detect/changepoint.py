"""Where did a characteristic start going wrong, and how?

Input is the deviation series in half-tolerance units (|1| = at the limit). PELT locates the
change in mean; CUSUM cross-checks it; the post-change slope separates a *step* (something
changed at once: a shift handover, a part lot) from a *drift* (something wears).

The onset reported for a drift is not the change point. Containment needs the moment parts
plausibly began failing, so for a drift we extrapolate the fitted ramp plus two residual sigmas
to the tolerance limit. That is deliberately conservative: an escape costs more than a hold.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import ruptures as rpt
from numpy.typing import NDArray

MIN_POINTS = 30  # below this, no change-point claim is statistically honest
MIN_SHIFT = 0.25  # half-tolerance units; smaller mean shifts are noise, not a finding
DRIFT_SLOPE_TOTAL = 0.3  # a post-change fit that rises this much over its span is a ramp
AGREEMENT_POINTS = 20  # PELT and CUSUM agreeing within this many points -> high confidence
CUSUM_K, CUSUM_H = 0.5, 5.0  # standard tabular CUSUM allowances (in sigma units)


class Verdict(StrEnum):
    NONE = "NONE"
    DRIFT = "DRIFT"
    STEP = "STEP"


@dataclass(frozen=True)
class DriftVerdict:
    verdict: Verdict
    change_index: int | None = None  # where the mean changed
    onset_index: int | None = None  # where parts plausibly started failing
    severity: str = "LOW"  # LOW < 0.5, MEDIUM < 1.0, HIGH >= 1.0 half-tolerance mean shift
    method: str = "pelt"
    confidence: float = 0.0
    evidence: dict[str, float] = field(default_factory=dict)


def detect_change(dev: NDArray[np.floating]) -> DriftVerdict:
    """Classify a deviation series as NONE, STEP or DRIFT with an onset index."""
    n = len(dev)
    if n < MIN_POINTS:
        return DriftVerdict(Verdict.NONE, evidence={"n": n})

    # Standardise on the opening fifth, which is the best available picture of "in control".
    base = dev[: max(MIN_POINTS // 2, n // 5)]
    sigma = float(np.std(base)) or 1e-9
    z = (dev - float(np.mean(base))) / sigma

    bkps = rpt.KernelCPD(kernel="linear", min_size=10).fit(z).predict(pen=3 * math.log(n))
    change = next((b for b in bkps if b < n), None)
    if change is None:
        return DriftVerdict(Verdict.NONE, evidence={"n": n})

    pre, post = dev[:change], dev[change:]
    shift = float(np.mean(post) - np.mean(pre))
    if abs(shift) < MIN_SHIFT:
        return DriftVerdict(Verdict.NONE, evidence={"n": n, "shift": shift})

    cusum = _cusum_alarm(z)
    confidence = 0.9 if cusum is not None and abs(cusum - change) <= AGREEMENT_POINTS else 0.6

    idx = np.arange(change, n)
    slope, intercept = np.polyfit(idx, post, 1)
    residual_sigma = float(np.std(post - (slope * idx + intercept)))
    is_drift = abs(slope) * len(post) > DRIFT_SLOPE_TOTAL

    if is_drift:
        # first index where fitted ramp + 2 sigma reaches the limit on the drifting side
        limit = math.copysign(1.0, shift)
        target = limit - math.copysign(2 * residual_sigma, shift)
        crossing = (target - intercept) / slope if slope else math.inf
        onset = int(min(max(crossing, change), n - 1))
    else:
        onset = change

    return DriftVerdict(
        verdict=Verdict.DRIFT if is_drift else Verdict.STEP,
        change_index=change,
        onset_index=onset,
        severity="LOW" if abs(shift) < 0.5 else "MEDIUM" if abs(shift) < 1.0 else "HIGH",
        confidence=confidence,
        evidence={
            "n": n,
            "shift": round(shift, 4),
            "slope_per_point": round(float(slope), 6),
            "residual_sigma": round(residual_sigma, 4),
            "pelt_index": change,
            "cusum_index": float("nan") if cusum is None else cusum,
        },
    )


def _cusum_alarm(z: NDArray[np.floating]) -> int | None:
    """Index of the first tabular-CUSUM alarm on either side, or None."""
    hi = lo = 0.0
    for i, v in enumerate(z):
        hi = max(0.0, hi + v - CUSUM_K)
        lo = max(0.0, lo - v - CUSUM_K)
        if hi > CUSUM_H or lo > CUSUM_H:
            return i
    return None
