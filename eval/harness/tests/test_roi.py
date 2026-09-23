"""The ROI page's numbers come from here, so they cannot drift from the prose."""

from dataclasses import fields

import pytest

from qgate_eval.roi import (
    DEFAULT,
    Assumptions,
    break_even_agreement,
    break_even_agreement_time_only,
    roi,
    sensitivity,
)

pytestmark = pytest.mark.unit


def test_every_assumption_carries_a_note() -> None:
    notes = Assumptions.notes()
    for f in fields(Assumptions):
        assert f.name in notes and len(notes[f.name]) > 20, f.name


def test_time_only_break_even_is_where_review_equals_time_saved() -> None:
    a = DEFAULT
    be = break_even_agreement_time_only(a)
    assert 0 < be < a.agreement_rate  # the measured rate clears it
    r = roi(Assumptions(**{**a.__dict__, "agreement_rate": be}))
    assert abs(r.engineer_min_saved_per_triage) < 1e-9


def test_full_break_even_is_where_net_is_zero_when_escapes_are_cheap() -> None:
    cheap = Assumptions(
        **{**DEFAULT.__dict__, "escape_cost_eur": 0.0, "good_vehicles_held_agent": 40.0}
    )
    be = break_even_agreement(cheap)
    assert 0 < be < 1
    assert abs(roi(Assumptions(**{**cheap.__dict__, "agreement_rate": be})).net_per_day_eur) < 1e-6


def test_a_worse_agreement_rate_never_helps() -> None:
    a = DEFAULT
    nets = [
        roi(Assumptions(**{**a.__dict__, "agreement_rate": g})).net_per_day_eur
        for g in (0.2, 0.5, 0.66, 0.9)
    ]
    assert nets == sorted(nets)


def test_sensitivity_spans_the_escape_cost_range_in_order() -> None:
    """Review Focus 2: halving the escape cost must show up, not be averaged away."""
    rows = sensitivity(DEFAULT, (5_000, 25_000, 50_000, 100_000, 500_000))
    assert [r.escape_cost_eur for r in rows] == [5_000, 25_000, 50_000, 100_000, 500_000]
    nets = [r.net_per_day_eur for r in rows]
    assert nets == sorted(nets)  # a costlier escape makes avoided escapes worth more
    assert rows[0].net_per_day_eur < rows[-1].net_per_day_eur


def test_default_agreement_rate_is_the_measured_one() -> None:
    assert DEFAULT.agreement_rate == pytest.approx(0.66)  # eval baseline, 50 goldens
    assert DEFAULT.model_cost_per_triage_eur == pytest.approx(0.0031, abs=0.0005)
