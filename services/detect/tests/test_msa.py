"""Measurement-system analysis. Deviations are in half-tolerance units; tolerance width is 2."""

import numpy as np
import pytest

from qgate_detect.msa import capability

pytestmark = pytest.mark.unit
rng = np.random.default_rng(0)


def repeats(n_vins: int, sigma: float) -> dict[str, list[float]]:
    """Per-VIN repeat readings around a per-VIN true value, gauge noise ``sigma``."""
    return {f"V{i}": list(rng.normal(rng.normal(0, 0.2), sigma, 3)) for i in range(n_vins)}


def test_tight_repeats_and_no_bias_is_capable() -> None:
    own, peers = rng.normal(0, 1 / 6, 300), rng.normal(0, 1 / 6, 600)
    c = capability("EOL-B1", repeats(20, 0.02), own, peers)
    assert c.capable is True
    assert c.grr_pct is not None and 4 < c.grr_pct < 9  # 6 * 0.02 / 2 * 100 = 6
    assert c.bias_vs_peers is not None and abs(c.bias_vs_peers) < 0.1


def test_biased_bench_is_not_capable_even_with_good_repeatability() -> None:
    own = rng.normal(0.9, 1 / 6, 300)  # reads 0.9 half-tolerance high
    peers = rng.normal(0, 1 / 6, 600)
    c = capability("EOL-B2", repeats(20, 0.02), own, peers)
    assert c.capable is False
    assert c.bias_vs_peers is not None and 0.75 < c.bias_vs_peers < 1.05
    assert c.grr_pct is not None and c.grr_pct < 30


def test_noisy_gauge_fails_grr() -> None:
    own, peers = rng.normal(0, 1 / 6, 300), rng.normal(0, 1 / 6, 600)
    c = capability("EOL-B3", repeats(20, 0.15), own, peers)  # 6 * 0.15 / 2 = 45 %
    assert c.capable is False and c.grr_pct is not None and c.grr_pct > 30


def test_no_repeats_still_yields_a_bias_verdict() -> None:
    """Review Focus 2: absence of R&R data must not crash or imply capability."""
    own, peers = rng.normal(0.9, 1 / 6, 300), rng.normal(0, 1 / 6, 600)
    c = capability("EOL-B2", {}, own, peers)
    assert c.grr_pct is None and c.n_repeats == 0
    assert c.capable is False and c.bias_vs_peers is not None


def test_too_little_data_is_undetermined_not_capable() -> None:
    c = capability("EOL-B1", {}, np.array([0.1, 0.0]), np.array([0.0]))
    assert c.capable is False and c.method == "insufficient-data"
