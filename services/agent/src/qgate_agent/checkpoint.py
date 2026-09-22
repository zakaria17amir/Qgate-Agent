"""The Postgres checkpointer, configured to (de)serialise our own state types.

LangGraph's serializer refuses unknown classes by default in future versions; listing ours is
both the fix and a statement of exactly what ends up in the checkpoint tables.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

ALLOWED = [
    ("qgate_agent.tools.models", "Genealogy"),
    ("qgate_agent.tools.models", "StationVisit"),
    ("qgate_agent.tools.models", "MeasurementRow"),
    ("qgate_agent.tools.models", "EolSummary"),
    ("qgate_agent.tools.models", "CorrelationResult"),
    ("qgate_agent.tools.models", "DriftResult"),
    ("qgate_agent.tools.models", "BenchResult"),
    ("qgate_agent.state", "Hypothesis"),
    ("qgate_agent.state", "Bounds"),
    ("qgate_agent.state", "HumanDecision"),
]


@contextmanager
def saver(database_url: str) -> Iterator[PostgresSaver]:
    """A ready checkpointer on the ``checkpoint`` schema (role ``checkpoint_rw`` in compose)."""
    url = (
        database_url
        + ("&" if "?" in database_url else "?")
        + "options=-c%20search_path%3Dcheckpoint"
    )
    with PostgresSaver.from_conn_string(url) as s:
        s.serde = JsonPlusSerializer(allowed_msgpack_modules=ALLOWED)
        s.setup()
        yield s
