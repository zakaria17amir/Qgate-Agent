"""What flows through the triage graph. Plain data; every node reads some of it and adds some."""

from datetime import datetime
from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from qgate_agent.tools.models import BenchResult, CorrelationResult, DriftResult, Genealogy

Kind = Literal["WINDOW", "LOT", "SINGLE", "NONE"]


class Hypothesis(BaseModel):
    station_id: str
    characteristic_id: str
    reasoning: str


class Hypotheses(BaseModel):
    """The model's ranking of the fault map's candidates — never a station outside the map."""

    ranked: list[Hypothesis] = Field(min_length=1)


class Order(BaseModel):
    text: str = Field(min_length=20)


class Explanation(BaseModel):
    text: str = Field(min_length=20)


class Bounds(BaseModel):
    kind: Kind
    station_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    lot_ids: list[str] = Field(default_factory=list)
    vins: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class HumanDecision(BaseModel):
    decision: Literal["APPROVE", "AMEND", "REJECT"]
    actor: str
    reason: str | None = None
    bounds: Bounds | None = None  # the amended bounds, when AMEND


class TriageState(TypedDict, total=False):
    # intake
    thread_id: str
    vin: str
    fault_codes: list[str]
    eol_ts: datetime
    golden_id: str | None
    # evidence
    genealogy: Genealogy
    hypotheses: list[Hypothesis]
    siblings: CorrelationResult
    drift: DriftResult
    bench: BenchResult
    # decision
    bounds: Bounds
    draft_order: str
    containment_id: str
    outcome: Literal[
        "PROPOSED", "ESCALATED", "NO_CONTAINMENT", "COMMITTED", "REJECTED", "COMMIT_PENDING"
    ]
    human: HumanDecision
    mes_ref: str
    # accounting
    timings_ms: dict[str, float]
    llm_ms: float
    prompt_tokens: int
    completion_tokens: int
    errors: list[str]
