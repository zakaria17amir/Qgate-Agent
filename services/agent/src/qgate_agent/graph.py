"""Wire the nine nodes into the triage graph (design §8.2) with a Postgres checkpointer.

Every node is wrapped to record its wall time, so the audit row can split latency into model
time and everything else. The gate node calls ``interrupt()``; with a checkpointer that means the
thread persists and can be resumed from any process (ADR-003).
"""

import time
from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from qgate_agent.nodes import Deps, make_nodes, route
from qgate_agent.state import TriageState

Node = Callable[[TriageState], dict[str, Any]]


def _timed(name: str, fn: Node) -> Node:
    def wrapped(s: TriageState) -> dict[str, Any]:
        t0 = time.perf_counter()
        update = fn(s)
        ms = (time.perf_counter() - t0) * 1000
        timings = {**s.get("timings_ms", {}), **update.get("timings_ms", {}), name: round(ms, 1)}
        return {**update, "timings_ms": timings}

    return wrapped


def build_graph(
    deps: Deps, checkpointer: BaseCheckpointSaver[Any]
) -> CompiledStateGraph[Any, Any, Any, Any]:
    g: StateGraph[TriageState] = StateGraph(TriageState)
    for name, fn in make_nodes(deps).items():
        g.add_node(name, _timed(name, fn))  # type: ignore[call-overload]  # dict-returning nodes are fine at runtime

    g.add_edge(START, "intake")
    g.add_edge("intake", "genealogy")
    g.add_edge("genealogy", "hypothesise")
    g.add_edge("hypothesise", "correlate")
    g.add_edge("correlate", "drift_check")
    g.add_conditional_edges("drift_check", route, ["bench_alert", "escalate", "bound"])
    g.add_edge("bound", "compose")
    g.add_edge("compose", "gate")
    # after the human: a rejection ends the thread; anything else writes to the plant
    g.add_conditional_edges(
        "gate", lambda s: "report" if s["outcome"] == "REJECTED" else "commit", ["report", "commit"]
    )
    g.add_edge("commit", "report")
    g.add_edge("bench_alert", "report")
    g.add_edge("escalate", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=checkpointer)
