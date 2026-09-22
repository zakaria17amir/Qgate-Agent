"""Only *message* problems go to the DLQ; an unreachable database must stop the consumer."""

from unittest.mock import MagicMock

import psycopg
import pytest

from qgate_ingest.main import handle

pytestmark = pytest.mark.unit


def _msg() -> MagicMock:
    m = MagicMock()
    m.topic.return_value = "line.eol.results"
    m.value.return_value = b"\x00garbage"
    m.offset.return_value = 7
    m.partition.return_value = 0
    m.key.return_value = b"SYN1"
    return m


def test_undecodable_message_is_parked_and_committed(monkeypatch: pytest.MonkeyPatch) -> None:
    dlq, conn = MagicMock(), MagicMock()
    monkeypatch.setattr(
        "qgate_ingest.main.kafka.decode", MagicMock(side_effect=ValueError("bad avro"))
    )
    parked = handle(MagicMock(), conn, dlq, _msg())
    assert parked is True
    conn.rollback.assert_called_once()
    dlq.produce.assert_called_once()


def test_database_outage_propagates_instead_of_parking(monkeypatch: pytest.MonkeyPatch) -> None:
    dlq = MagicMock()
    conn = MagicMock()
    conn.commit.side_effect = psycopg.OperationalError("server closed the connection")
    monkeypatch.setattr("qgate_ingest.main.kafka.decode", MagicMock())
    monkeypatch.setattr("qgate_ingest.main._as_line_record", MagicMock())
    monkeypatch.setattr("qgate_ingest.main.upsert", MagicMock())
    with pytest.raises(psycopg.OperationalError):
        handle(MagicMock(), conn, dlq, _msg())
    dlq.produce.assert_not_called()


def test_a_parked_message_is_counted_as_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    from prometheus_client import generate_latest

    from qgate_core import metrics

    monkeypatch.setattr(
        "qgate_ingest.main.kafka.decode", MagicMock(side_effect=ValueError("bad avro"))
    )
    handle(MagicMock(), MagicMock(), MagicMock(), _msg())
    text = generate_latest(metrics.REGISTRY).decode()
    assert 'ingest_records_total{result="dlq",topic="line.eol.results"}' in text
