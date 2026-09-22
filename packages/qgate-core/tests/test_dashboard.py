"""The dashboard may only ask for metrics somebody emits (Phase 5 Review Focus 2)."""

import json
import re
from pathlib import Path

import pytest

from qgate_core import metrics

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[3]
DASHBOARD = ROOT / "observability" / "grafana" / "dashboards" / "qgate.json"
EXTERNAL_PREFIXES = ("redpanda_", "process_", "up", "kafka_consumer_lag", "line_sim_")
SUFFIXES = ("_bucket", "_count", "_sum", "_total", "_created")


def _exprs(panels: list[dict]) -> list[str]:  # type: ignore[type-arg]
    out = []
    for p in panels:
        out += [t["expr"] for t in p.get("targets", []) if "expr" in t]
        out += _exprs(p.get("panels", []))
    return out


def test_every_panel_queries_a_contract_metric() -> None:
    dash = json.loads(DASHBOARD.read_text(encoding="utf8"))
    exprs = _exprs(dash["panels"])
    assert len(exprs) >= 8, "the §11 panel list is longer than this"
    known = set(metrics.NAMES)
    for expr in exprs:
        names = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s*(?:\{|\[|$|\))", expr))
        names = {n for n in names if "_" in n or n == "up"}  # PromQL functions have no underscore
        for name in names:
            base = name
            for suffix in SUFFIXES:
                if base.endswith(suffix) and base[: -len(suffix)] in known:
                    base = base[: -len(suffix)]
            assert base in known or base.startswith(EXTERNAL_PREFIXES), f"{name!r} in {expr!r}"


def test_dashboard_is_provisioned_with_a_stable_uid() -> None:
    dash = json.loads(DASHBOARD.read_text(encoding="utf8"))
    assert dash["uid"] == "qgate" and dash["title"]
    titles = [p["title"] for p in dash["panels"]]
    for wanted in ("lag", "latency", "gate", "outcome", "cost", "breaker", "error", "SLO"):
        assert any(wanted.lower() in t.lower() for t in titles), wanted
