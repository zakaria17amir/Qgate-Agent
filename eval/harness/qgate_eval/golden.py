"""The golden-case contract: one YAML per case in ``eval/goldens``.

A golden names a scenario + seed (so the stream is reproducible), the failing VIN that starts a
triage, the decision a correct agent must reach, and what the stand-in human does at the gate.
"""

from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, Field


class Decision(StrEnum):
    SINGLE = "SINGLE"  # hold this vehicle only
    WINDOW = "WINDOW"  # hold a build window at one station
    LOT = "LOT"  # hold every carrier of a parts lot
    NONE = "NONE"  # hold nothing: the bench is wrong
    ESCALATE = "ESCALATE"  # evidence contradicts; no proposal
    MULTI = "MULTI"  # two independent containments


class Family(StrEnum):
    ISOLATED = "isolated"
    DRIFT = "drift"
    LOT = "lot"
    BENCH = "bench"
    CONTRADICTORY = "contradictory"
    OVERLAP = "overlap"


class Trigger(BaseModel):
    vin: str
    fault_codes: list[str]


class Expected(BaseModel):
    decision: Decision
    station_id: str | None = None
    window_start_sequence: int | None = None
    tolerance_takts: int = 15
    lot_ids: list[str] = Field(default_factory=list)


class Human(BaseModel):
    action: str = "APPROVE"  # APPROVE | AMEND | REJECT — what the harness does at the gate
    amend_start_delta_takts: int | None = None
    reason: str | None = None


class Golden(BaseModel):
    id: str
    family: Family
    scenario: str
    seed: int
    trigger: Trigger
    expected: Expected
    human: Human = Field(default_factory=Human)
    notes: str = ""

    @classmethod
    def load(cls, path: Path) -> Self:
        with path.open(encoding="utf8") as f:
            return cls.model_validate(yaml.safe_load(f))

    def dump(self, path: Path) -> None:
        with path.open("w", encoding="utf8", newline="") as f:
            yaml.safe_dump(self.model_dump(mode="json"), f, sort_keys=False, width=100)


def load_all(directory: Path) -> list[Golden]:
    return [Golden.load(p) for p in sorted(directory.glob("*.yaml"))]
