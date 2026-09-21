"""Turn a line and a scenario into a takt-ordered event stream with declared ground truth.

Two value layers matter here. The *true* value is what the part actually is; the *reported*
value is what the gauge said. Injects of kind ``drift``/``step``/``lot``/``noise`` change the
true value, ``bench_bias`` changes only the reported EOL value. Ground truth is defined on
true values, EOL verdicts on reported ones — that gap is what the bench-fault scenarios test.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

from qgate_core.models import BuildEvent, EolResult, LineRecord, Measurement, Result
from qgate_generator.line import Bench, Characteristic, Line
from qgate_generator.scenario import Inject, Scenario

EPOCH = datetime(2026, 1, 5, 6, 0, tzinfo=UTC)  # a Monday at the start of the early shift
PROCESS_SIGMA = 1 / 6  # true-value noise as a fraction of half-tolerance (a capable line, Cp = 2)
BASE_DEFECT_MAGNITUDE = 1.5  # random one-off defects land clearly outside the band
REPEAT_SAMPLE = 0.05  # share of vehicles re-measured at EOL for gauge R&R
REPEAT_NUMBERS = (2, 3)
LOT_BLOCK = 25  # vehicles per lot bin; lots rotate so one lot's carriers are interleaved
LOT_COUNT = 8


@dataclass(frozen=True)
class GroundTruth:
    """What is *actually* wrong, independent of what any gauge reported."""

    defective_vins: frozenset[str]
    by_inject: dict[int, frozenset[str]]  # inject index -> VINs it pushed out of tolerance
    bench_fault: bool


@dataclass
class Run:
    events: list[LineRecord]
    truth: GroundTruth


def vin_of(sequence_no: int) -> str:
    return f"SYN{sequence_no:014d}"


def lot_id(station_id: str, sequence_no: int) -> str:
    return f"L-{station_id[-2:]}-{(sequence_no // LOT_BLOCK) % LOT_COUNT:04d}"


def _ramp(inject: Inject, sequence_no: int) -> float:
    """Inject magnitude at ``sequence_no``: 0 before start, linear to full at end, then flat."""
    if sequence_no < inject.start_sequence:
        return 0.0
    if inject.end_sequence is None or sequence_no >= inject.end_sequence:
        return inject.magnitude
    span = inject.end_sequence - inject.start_sequence
    return inject.magnitude * (sequence_no - inject.start_sequence) / span


def _applies(inject: Inject, c: Characteristic, seq: int, lots: set[str]) -> bool:
    if inject.station_id != c.station_id:
        return False
    if inject.characteristic_id not in (None, c.id):
        return False
    if inject.kind == "lot":
        return inject.lot_id in lots
    end = inject.end_sequence if inject.kind == "noise" else None
    return seq >= inject.start_sequence and (end is None or seq < end)


def generate(line: Line, scenario: Scenario, start: datetime = EPOCH) -> Run:
    rng = np.random.default_rng(scenario.seed)
    takt = timedelta(seconds=line.takt_s)
    stations = sorted(line.stations, key=lambda s: s.sequence_pos)
    eol = line.eol_station
    chars = [c for s in stations for c in s.characteristics]
    n_veh = scenario.vehicles

    # --- draw every random number vehicle-major so the stream is a pure function of the seed
    noise = rng.normal(0.0, PROCESS_SIGMA, size=(n_veh, len(chars)))
    shared = rng.normal(0.0, 1.0, size=n_veh)  # per-vehicle term for ``noise`` injects
    base_defect = rng.random(n_veh) < scenario.base_defect_rate
    defect_char = rng.integers(0, len(chars), size=n_veh)
    defect_sign = rng.choice([-1.0, 1.0], size=n_veh)
    repeat_sample = rng.random(n_veh) < REPEAT_SAMPLE
    bench_noise = rng.normal(0.0, 1.0, size=(n_veh, len(chars), 1 + len(REPEAT_NUMBERS)))

    truth_defective: set[str] = set()
    by_inject: dict[int, set[str]] = {i: set() for i in range(len(scenario.injects))}
    bench_fault = any(i.kind == "bench_bias" for i in scenario.injects)

    # reported[n][c] -> list of reported values (index 0 is the primary measurement)
    reported: list[dict[str, list[float]]] = []
    faults: list[set[str]] = []
    benches: list[Bench] = []
    for n in range(n_veh):
        vin = vin_of(n)
        bench = line.eol_benches[n % len(line.eol_benches)]
        benches.append(bench)
        lots = {lot_id(s.id, n) for s in stations if s.fits_lot}
        vehicle_reported: dict[str, list[float]] = {}
        vehicle_faults: set[str] = set()
        for ci, c in enumerate(chars):
            ht = c.half_tolerance
            true = c.nominal + noise[n, ci] * ht
            if base_defect[n] and defect_char[n] == ci:
                true += defect_sign[n] * BASE_DEFECT_MAGNITUDE * ht
            bias = 0.0
            for ii, inj in enumerate(scenario.injects):
                if not _applies(inj, c, n, lots):
                    continue
                if inj.kind == "bench_bias":
                    if inj.bench_id == bench.id and c.station_id == eol.id:
                        bias += _ramp(inj, n) * ht
                    continue
                delta = (
                    shared[n] * inj.magnitude * ht if inj.kind == "noise" else _ramp(inj, n) * ht
                )
                before = true
                true += delta
                if _oot(true, c) and not _oot(before, c):
                    by_inject[ii].add(vin)
            if _oot(true, c):
                truth_defective.add(vin)
                vehicle_faults.add(f"F-{c.station_id[-2:]}")
            # the gauge: inline stations report the true value; the EOL bench adds bias and noise
            if c.station_id == eol.id:
                sigma = bench.repeatability_sigma * ht
                n_rep = 1 + len(REPEAT_NUMBERS) if repeat_sample[n] else 1
                values = [true + bias + bench_noise[n, ci, r] * sigma for r in range(n_rep)]
                if _oot(values[0], c):
                    vehicle_faults.add(f"F-{c.station_id[-2:]}")
            else:
                values = [true]
            vehicle_reported[c.id] = values
        reported.append(vehicle_reported)
        faults.append(vehicle_faults)

    # --- emit in takt order: at tick t, station k holds vehicle t - k
    events: list[LineRecord] = []
    for t in range(n_veh + len(stations) - 1):
        at = start + t * takt
        shift = line.shift_at_hour(at.hour)
        for k, s in enumerate(stations):
            n = t - k
            if not 0 <= n < n_veh:
                continue
            vin = vin_of(n)
            bench_id = benches[n].id if s.id == eol.id else "INLINE"
            events.append(
                BuildEvent(
                    vin=vin,
                    station_id=s.id,
                    sequence_no=n,
                    entered_at=at,
                    shift_id=shift.id,
                    operator_id=f"OP-{s.id[-2:]}-{shift.crew}",
                    parts_lots=[lot_id(s.id, n)] if s.fits_lot else [],
                )
            )
            for c in s.characteristics:
                for r, value in enumerate(reported[n][c.id]):
                    events.append(
                        Measurement(
                            vin=vin,
                            station_id=s.id,
                            characteristic_id=c.id,
                            bench_id=bench_id,
                            measured_at=at,
                            value=round(value, 4),
                            unit=c.unit,
                            nominal=c.nominal,
                            lower_limit=c.lower_limit,
                            upper_limit=c.upper_limit,
                            repeat_no=1 if r == 0 else REPEAT_NUMBERS[r - 1],
                        )
                    )
            if s.id == eol.id:
                codes = sorted(faults[n])
                events.append(
                    EolResult(
                        vin=vin,
                        tested_at=at,
                        bench_id=bench_id,
                        result=Result.FAIL if codes else Result.PASS,
                        fault_codes=codes,
                    )
                )

    truth = GroundTruth(
        defective_vins=frozenset(truth_defective),
        by_inject={i: frozenset(v) for i, v in by_inject.items()},
        bench_fault=bench_fault,
    )
    return Run(events=events, truth=truth)


def _oot(value: float, c: Characteristic) -> bool:
    return value < c.lower_limit or value > c.upper_limit
