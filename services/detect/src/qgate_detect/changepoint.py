"""Where did a characteristic start going wrong, and how?

Input is the deviation series in half-tolerance units (|1| = at the limit). PELT locates the
change in mean; CUSUM cross-checks it; the post-change slope separates a *step* (something
changed at once: a shift handover, a part lot) from a *drift* (something wears).

The onset reported for a drift is not the change point. Containment needs the moment parts
began failing: the first out-of-tolerance reading after the change that the fitted ramp makes
plausible *is* the onset (inline gauges report the part as it is). Only when nothing has failed
yet do we extrapolate the fitted ramp plus two residual sigmas to the limit — deliberately
conservative, because an escape costs more than a hold.
"""

import math
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import ruptures as rpt
from numpy.typing import NDArray

MIN_POINTS = 30  # below this, no change-point claim is statistically honest
MIN_SHIFT = 0.25  # half-tolerance units; smaller mean shifts are noise, not a finding
DRIFT_SLOPE_T = 4.0  # slope / standard error; ~N(0,1) for a step, far larger for a ramp
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

    bkps = [
        int(b)
        for b in rpt.KernelCPD(kernel="linear", min_size=10).fit(z).predict(pen=3 * math.log(n))
    ]
    change = next((b for b in bkps if b < n), None)
    if change is None:
        return DriftVerdict(Verdict.NONE, evidence={"n": n})

    pre, post = dev[:change], dev[change:]
    shift = float(np.mean(post) - np.mean(pre))
    if abs(shift) < MIN_SHIFT:
        return DriftVerdict(Verdict.NONE, evidence={"n": n, "shift": shift})

    cusum = _cusum_alarm(z)
    confidence = 0.9 if cusum is not None and abs(cusum - change) <= AGREEMENT_POINTS else 0.6

    # A ramp that later plateaus (tool replaced, saturation) would flatten a whole-tail fit and
    # bias the onset early, so a flat final segment is excluded from the fit.
    segment_end = _without_flat_tail(dev, bkps, change, n)
    idx = np.arange(change, segment_end)
    segment = dev[change:segment_end]
    slope, intercept, residual_sigma, slope_t = _fit(idx, segment)
    is_drift = slope_t > DRIFT_SLOPE_T

    onset_method = 0.0  # 0 = change point, 1 = first observed out-of-tolerance, 2 = extrapolated
    if is_drift:
        side = math.copysign(1.0, shift)
        # an out-of-tolerance reading counts as the onset only if the ramp makes it plausible;
        # a lone random defect long before the ramp reaches the band is not where wear began
        fitted = slope * np.arange(change, n) + intercept
        plausible = side * (fitted + side * 3 * residual_sigma) >= 1.0
        failed = np.flatnonzero((side * post >= 1.0) & plausible)
        if failed.size:
            onset, onset_method = change + int(failed[0]), 1.0
        else:
            # nobody has failed yet: where would fitted ramp + 2 sigma reach the limit?
            target = side - side * 2 * residual_sigma
            crossing = (target - intercept) / slope if slope else math.inf
            onset, onset_method = int(min(max(crossing, change), segment_end - 1)), 2.0
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
            "slope_t": round(slope_t, 2),
            "onset_method": onset_method,
            "residual_sigma": round(residual_sigma, 4),
            "pelt_index": change,
            "cusum_index": float("nan") if cusum is None else cusum,
        },
    )


def _fit(idx: NDArray[np.integer], y: NDArray[np.floating]) -> tuple[float, float, float, float]:
    """Least-squares line: slope, intercept, residual sigma, |t| of the slope."""
    slope, intercept = np.polyfit(idx, y, 1)
    residual_sigma = float(np.std(y - (slope * idx + intercept)))
    se = residual_sigma / math.sqrt(float(np.sum((idx - idx.mean()) ** 2)) or 1.0)
    return float(slope), float(intercept), residual_sigma, abs(float(slope)) / (se or 1e-12)


def _without_flat_tail(dev: NDArray[np.floating], bkps: list[int], change: int, n: int) -> int:
    """End of the region to fit: drop the last PELT segment if it is flat (a plateau)."""
    inner = [b for b in bkps if change < b < n]
    if not inner:
        return n
    tail_start = inner[-1]
    tail_idx = np.arange(tail_start, n)
    if len(tail_idx) >= 10 and _fit(tail_idx, dev[tail_start:])[3] < DRIFT_SLOPE_T:
        return tail_start
    return n


def _cusum_alarm(z: NDArray[np.floating]) -> int | None:
    """Index of the first tabular-CUSUM alarm on either side, or None."""
    hi = lo = 0.0
    for i, v in enumerate(z):
        hi = max(0.0, hi + v - CUSUM_K)
        lo = max(0.0, lo - v - CUSUM_K)
        if hi > CUSUM_H or lo > CUSUM_H:
            return i
    return None
