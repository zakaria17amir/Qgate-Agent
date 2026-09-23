"""The ROI model behind ``docs/roi.md``. Every input is an assumption and says so.

Two costs against each other per triage: the engineer minutes the agent saves (a proposal the
reviewer agrees with replaces the manual triage; one they amend or reject costs the review *and*
the manual triage they then do anyway), and the escape asymmetry (an escape to a customer versus
holding good vehicles). Synthetic data throughout: nothing here is a plant figure; the notes say
where each number came from.
"""

from dataclasses import dataclass, fields
from typing import ClassVar


@dataclass(frozen=True)
class Assumptions:
    manual_triage_min: float = 25.0
    review_min: float = 4.0
    engineer_eur_per_h: float = 70.0
    agreement_rate: float = 0.66
    triages_per_day: float = 12.0
    escape_rate_manual: float = 0.02
    escape_rate_agent: float = 0.01
    escape_cost_eur: float = 50_000.0
    good_vehicles_held_manual: float = 40.0
    good_vehicles_held_agent: float = 25.0
    hold_cost_per_vehicle_eur: float = 60.0
    model_cost_per_triage_eur: float = 0.0031

    NOTES: ClassVar[dict[str, str]] = {
        "manual_triage_min": "Minutes a quality engineer spends pulling genealogy, siblings and "
        "gauge history by hand before deciding. Assumed; interview any EOL engineer for theirs.",
        "review_min": "Minutes to read a proposal (order, window, siblings, bench) and decide. "
        "Assumed from the console's case page; the audit table records the real value. When the "
        "reviewer amends or rejects, the manual triage is assumed to happen as well "
        "(conservative).",
        "engineer_eur_per_h": "Loaded hourly cost of a quality engineer. Assumed; a round number.",
        "agreement_rate": "Share of proposals approved unamended. MEASURED on the fifty goldens "
        "(eval baseline, 2026-09-22): 0.66. The one number here that is not assumed.",
        "triages_per_day": "EOL failures needing a containment decision per day on one line. "
        "Assumed for a ~1 000-vehicle/day line at ~1 % first-pass fail.",
        "escape_rate_manual": "Probability a manual decision lets a defective vehicle escape "
        "(too-narrow window). Assumed; nobody publishes this.",
        "escape_rate_agent": "Same with the agent's proposal reviewed by a human. Assumed at "
        "half: the goldens show recall 0.96 on non-overlap families, but that is synthetic.",
        "escape_cost_eur": "Cost of one escape reaching a customer: field action, warranty, "
        "reputation. The number nobody knows — see the sensitivity table.",
        "good_vehicles_held_manual": "Good vehicles quarantined per containment decided by hand "
        "(wide windows to be safe). Assumed.",
        "good_vehicles_held_agent": "Same with a bounded window from drift onset. Assumed from "
        "the goldens' precision 0.59 — it is not dramatically tighter, and says so.",
        "hold_cost_per_vehicle_eur": "Cost of holding and re-inspecting one good vehicle. Assumed.",
        "model_cost_per_triage_eur": "MEASURED: mean model spend per triage from the live runs "
        "($0.0031, price table is itself an assumption).",
    }

    @classmethod
    def notes(cls) -> dict[str, str]:
        return dict(cls.NOTES)


@dataclass(frozen=True)
class Result:
    agreement_rate: float
    escape_cost_eur: float
    engineer_min_saved_per_triage: float
    engineer_eur_saved_per_day: float
    escape_eur_avoided_per_day: float
    hold_eur_saved_per_day: float
    model_eur_per_day: float
    net_per_day_eur: float


def roi(a: Assumptions) -> Result:
    """Net EUR per day: engineer time saved + escapes avoided + fewer good vehicles held - model."""
    # agree: review replaces the manual triage; disagree: review plus the manual triage anyway
    saved_min = a.agreement_rate * a.manual_triage_min - a.review_min
    engineer = saved_min / 60 * a.engineer_eur_per_h * a.triages_per_day
    escapes = (a.escape_rate_manual - a.escape_rate_agent) * a.escape_cost_eur * a.triages_per_day
    holds = (
        (a.good_vehicles_held_manual - a.good_vehicles_held_agent)
        * a.hold_cost_per_vehicle_eur
        * a.triages_per_day
    )
    model = a.model_cost_per_triage_eur * a.triages_per_day
    return Result(
        a.agreement_rate,
        a.escape_cost_eur,
        saved_min,
        engineer,
        escapes,
        holds,
        model,
        engineer + escapes + holds - model,
    )


def break_even_agreement_time_only(a: Assumptions) -> float:
    """The spec's question: below which agreement rate does the agent cost the engineers more
    review time than it saves them? Escapes and holds ignored."""
    return a.review_min / a.manual_triage_min


def break_even_agreement(a: Assumptions) -> float:
    """Agreement rate at which the full net is zero. Linear in the rate, so solved directly;
    0 means the escape and hold terms alone pay for it under these assumptions."""
    lo, hi = roi(replace(a, 0.0)).net_per_day_eur, roi(replace(a, 1.0)).net_per_day_eur
    return max(0.0, min(1.0, -lo / (hi - lo)))


def sensitivity(a: Assumptions, escape_costs: tuple[float, ...]) -> list[Result]:
    return [roi(Assumptions(**{**a.__dict__, "escape_cost_eur": c})) for c in escape_costs]


def replace(a: Assumptions, agreement_rate: float) -> Assumptions:
    return Assumptions(**{**a.__dict__, "agreement_rate": agreement_rate})


DEFAULT = Assumptions()


def markdown(a: Assumptions = DEFAULT) -> str:
    """The tables docs/roi.md quotes."""
    r = roi(a)
    lines = ["| Assumption | Value | Where it comes from |", "|---|---|---|"]
    for f in fields(Assumptions):
        v = getattr(a, f.name)
        lines.append(f"| `{f.name}` | {v:g} | {a.NOTES[f.name]} |")
    lines += [
        "",
        "| Result (per day, one line) | EUR |",
        "|---|---|",
        f"| Engineer time saved ({r.engineer_min_saved_per_triage:.1f} min per triage) | "
        f"{r.engineer_eur_saved_per_day:,.0f} |",
        f"| Escapes avoided (expected value) | {r.escape_eur_avoided_per_day:,.0f} |",
        f"| Fewer good vehicles held | {r.hold_eur_saved_per_day:,.0f} |",
        f"| Model spend | -{r.model_eur_per_day:,.2f} |",
        f"| **Net** | **{r.net_per_day_eur:,.0f}** |",
        "",
        f"Break-even agreement rate on engineer time alone: "
        f"**{break_even_agreement_time_only(a):.2f}** (review / manual minutes); on the full "
        f"net: **{break_even_agreement(a):.2f}** (0 = the escape and hold terms pay for it at "
        f"any rate). Measured today: {a.agreement_rate:.2f}.",
        "",
        "| Escape cost (EUR) | Escapes avoided / day | Net / day |",
        "|---|---|---|",
    ]
    for s in sensitivity(a, (5_000, 25_000, 50_000, 100_000, 500_000)):
        lines.append(
            f"| {s.escape_cost_eur:,.0f} | {s.escape_eur_avoided_per_day:,.0f} | "
            f"{s.net_per_day_eur:,.0f} |"
        )
    return "\n".join(lines) + "\n"
