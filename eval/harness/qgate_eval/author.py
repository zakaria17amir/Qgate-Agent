"""Author the fifty golden cases from generator ground truth.

The agent does not exist yet; every expectation here comes from what the generator *knows* it
injected, so the goldens cannot encode agent behaviour. Re-running this is a deliberate,
reviewed change to the frozen set.
"""

from pathlib import Path

from qgate_core.models import EolResult, Result
from qgate_eval.golden import Decision, Expected, Family, Golden, Human, Trigger
from qgate_generator.line import Line
from qgate_generator.scenario import Scenario
from qgate_generator.stream import Run, generate

COUNTS = {
    Family.ISOLATED: 12,
    Family.DRIFT: 12,
    Family.LOT: 8,
    Family.BENCH: 8,
    Family.CONTRADICTORY: 6,
    Family.OVERLAP: 4,
}
SCENARIO_OF = {
    Family.ISOLATED: "clean_baseline",
    Family.DRIFT: "tool_wear",
    Family.LOT: "bad_lot",
    Family.BENCH: "bench_drift",
    Family.CONTRADICTORY: "shift_step",
    Family.OVERLAP: "overlap",
}


def seq(vin: str) -> int:
    return int(vin[3:])


def author(scenarios_dir: Path, out: Path) -> list[Golden]:
    line = Line.load(scenarios_dir / "line.yaml")
    goldens: list[Golden] = []
    for family, count in COUNTS.items():
        base = Scenario.load(scenarios_dir / f"{SCENARIO_OF[family]}.yaml", line)
        for i in range(1, count + 1):
            run = generate(line, base.model_copy(update={"seed": i}))
            goldens.append(_case(family, i, base, run))
    out.mkdir(parents=True, exist_ok=True)
    for g in goldens:
        g.dump(out / f"{g.id}.yaml")
    return goldens


def _case(family: Family, seed: int, scenario: Scenario, run: Run) -> Golden:
    fails = {e.vin: e for e in run.events if isinstance(e, EolResult) and e.result is Result.FAIL}
    truth = run.truth
    ordered = sorted(fails, key=seq)
    gid = f"{family.value}-{seed:02d}"
    human = Human()
    notes = ""

    if family is Family.ISOLATED:
        vin = next(v for v in ordered if v in truth.defective_vins)
        code = fails[vin].fault_codes[0]
        expected = Expected(decision=Decision.SINGLE, station_id=f"ST-{code[-2:]}")
        notes = "A one-off defect with no siblings; anything wider than one vehicle over-holds."

    elif family is Family.DRIFT:
        caused = sorted(truth.by_inject[0], key=seq)
        onset = seq(caused[0])
        vin = caused[min(4, len(caused) - 1)]  # a few failures in, so a run is visible
        expected = Expected(
            decision=Decision.WINDOW,
            station_id=scenario.injects[0].station_id,
            window_start_sequence=onset,
            tolerance_takts=15,
        )
        if seed <= 2:
            human = Human(
                action="AMEND",
                amend_start_delta_takts=-10,
                reason="widen to be safe near the fuzzy onset",
            )
        notes = "Gradual tool wear; the window starts at the first true out-of-tolerance vehicle."

    elif family is Family.LOT:
        carriers = sorted(truth.by_inject[0], key=seq)
        # deep enough into the lot that earlier carriers have reached EOL and failed too
        vin = carriers[min(40, len(carriers) - 1)]
        expected = Expected(
            decision=Decision.LOT,
            station_id=scenario.injects[0].station_id,
            lot_ids=[scenario.injects[0].lot_id or ""],
        )
        if seed == 1:
            human = Human(action="REJECT", reason="lot already quarantined by incoming inspection")
        notes = "Carriers are interleaved with good lots; a time window is the wrong shape."

    elif family is Family.BENCH:
        false_fails = [v for v in ordered if v not in truth.defective_vins and seq(v) >= 1100]
        vin = false_fails[0]
        expected = Expected(decision=Decision.NONE, station_id=scenario.injects[0].station_id)
        notes = "The bench drifted; the car is good. Propose nothing and flag the bench."

    elif family is Family.CONTRADICTORY:
        vin = sorted(truth.by_inject[0], key=seq)[0]  # the very first step-caused failure
        expected = Expected(decision=Decision.ESCALATE, station_id=scenario.injects[0].station_id)
        notes = "A step just happened: detect sees it, correlate finds no siblings yet. Escalate."

    else:  # OVERLAP
        drift_onset = seq(sorted(truth.by_inject[1], key=seq)[0])
        carriers = [v for v in sorted(truth.by_inject[0], key=seq) if seq(v) > drift_onset + 50]
        vin = carriers[0]
        expected = Expected(
            decision=Decision.MULTI,
            station_id=scenario.injects[0].station_id,
            lot_ids=[scenario.injects[0].lot_id or ""],
            window_start_sequence=drift_onset,
            tolerance_takts=15,
        )
        notes = "A bad lot inside a drift window: two containments, not one merged blob."

    return Golden(
        id=gid,
        family=family,
        scenario=scenario.id,
        seed=seed,
        trigger=Trigger(vin=vin, fault_codes=fails[vin].fault_codes),
        expected=expected,
        human=human,
        notes=notes,
    )
