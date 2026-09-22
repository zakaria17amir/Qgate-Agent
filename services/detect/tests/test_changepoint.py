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
    # observed first out-of-tolerance point lies near where ramp + 2 sigma crosses 1.0 (~1000)
    assert v.onset_index is not None and abs(v.onset_index - 1000) <= 40
    assert v.severity == "HIGH"


def test_drift_onset_is_the_first_observed_out_of_tolerance_point() -> None:
    """When parts have already failed, the data says who failed first; no extrapolation needed."""
    dev = noise(1500, 5)
    dev += np.clip((np.arange(1500) - 800) / 600, 0, None) * 2.0
    first_oot = int(np.argmax((dev >= 1.0) & (np.arange(1500) > 850)))
    v = detect_change(dev)
    assert v.verdict is Verdict.DRIFT and v.onset_index == first_oot
    assert v.evidence["onset_method"] == 1.0  # observed, not extrapolated


def test_a_lone_early_defect_is_not_mistaken_for_the_onset() -> None:
    dev = noise(1500, 6)
    dev += np.clip((np.arange(1500) - 800) / 600, 0, None) * 2.0
    dev[840] = 1.4  # one random defect while the ramp is still far from the band
    v = detect_change(dev)
    assert v.verdict is Verdict.DRIFT and v.onset_index is not None and v.onset_index > 900


def test_ramp_that_plateaus_is_still_located_from_its_rising_part() -> None:
    """Real tool wear stops rising when the tool is replaced or the ramp saturates."""
    dev = noise(2000, 4)
    ramp = np.clip((np.arange(2000) - 800) / 600, 0, 1) * 2.0  # rises 800..1400, flat after
    dev += ramp
    v = detect_change(dev)
    assert v.verdict is Verdict.DRIFT
    assert v.onset_index is not None and abs(v.onset_index - 1000) <= 40


def test_verdict_is_deterministic() -> None:
    dev = noise(800, 3)
    dev[400:] += 0.6
    assert detect_change(dev) == detect_change(dev)
