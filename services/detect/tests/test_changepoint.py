"""Series are in half-tolerance units, like the generator: |dev| > 1 is out of tolerance."""

import numpy as np
import pytest

from qgate_detect.changepoint import Verdict, detect_change

pytestmark = pytest.mark.unit
SIGMA = 1 / 6  # the generator's process noise as a fraction of half-tolerance


def noise(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(0.0, SIGMA, n)


def test_white_noise_is_no_change() -> None:
    v = detect_change(noise(1500))
    assert v.verdict is Verdict.NONE and v.onset_index is None


def test_too_few_points_is_no_change_with_evidence() -> None:
    v = detect_change(noise(12))
    assert v.verdict is Verdict.NONE and v.evidence["n"] == 12


def test_step_is_located_and_classified() -> None:
    dev = noise(1500, 1)
    dev[700:] += 0.8
    v = detect_change(dev)
    assert v.verdict is Verdict.STEP
    assert v.onset_index is not None and abs(v.onset_index - 700) <= 10
    assert v.severity == "MEDIUM"  # 0.8 half-tolerance shift


def test_ramp_onset_is_where_parts_plausibly_start_failing() -> None:
    dev = noise(1500, 2)
    ramp = np.clip((np.arange(1500) - 800) / 600, 0, None) * 2.0  # 0 -> 2.0 over 800..1400
    dev += ramp
    v = detect_change(dev)
    assert v.verdict is Verdict.DRIFT
    # earliest plausibly-defective: ramp + 2 sigma crosses 1.0 -> ramp = 0.667 -> index 1000
    assert v.onset_index is not None and abs(v.onset_index - 1000) <= 25
    assert v.severity == "HIGH"


def test_verdict_is_deterministic() -> None:
    dev = noise(800, 3)
    dev[400:] += 0.6
    assert detect_change(dev) == detect_change(dev)
