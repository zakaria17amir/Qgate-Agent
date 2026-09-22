import numpy as np
import pytest

from qgate_detect.spc import ewma_breaches, western_electric

pytestmark = pytest.mark.unit


def test_rule_1_single_point_beyond_3_sigma() -> None:
    z = np.zeros(20)
    z[7] = 3.5
    assert (1, 7) in {(v.rule, v.index) for v in western_electric(z)}


def test_rule_2_two_of_three_beyond_2_sigma_same_side() -> None:
    z = np.zeros(20)
    z[5], z[7] = 2.2, 2.4
    assert (2, 7) in {(v.rule, v.index) for v in western_electric(z)}


def test_rule_3_four_of_five_beyond_1_sigma_same_side() -> None:
    z = np.zeros(20)
    z[10:14] = -1.3
    assert (3, 13) in {(v.rule, v.index) for v in western_electric(z)}


def test_rule_4_eight_in_a_row_same_side() -> None:
    z = np.zeros(20)
    z[3:11] = 0.4
    assert (4, 10) in {(v.rule, v.index) for v in western_electric(z)}


def test_quiet_series_has_no_violations() -> None:
    z = np.random.default_rng(1).normal(size=200) * 0.6
    assert western_electric(z) == []


def test_ewma_catches_a_one_sigma_step_and_ignores_noise() -> None:
    rng = np.random.default_rng(2)
    noise = rng.normal(size=300)
    assert not ewma_breaches(noise).any()
    stepped = noise.copy()
    stepped[150:] += 1.0
    first = int(np.argmax(ewma_breaches(stepped)))
    assert 150 <= first <= 175
