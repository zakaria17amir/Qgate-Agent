"""Avro contracts: load ``schemas/<topic>.v1.avsc`` and convert records to and from bytes.

``to_avro``/``from_avro`` are registry-free (plain fastavro) and exist for tests and the DLQ.
Producers and consumers use the Confluent wire format via :mod:`qgate_core.kafka`.
"""

import io
import json
from typing import Any, cast

from fastavro import parse_schema, schemaless_reader, schemaless_writer
from pydantic import BaseModel

from qgate_core.settings import Settings


def load_schema(topic: str, version: int = 1) -> dict[str, Any]:
    path = Settings().schemas_dir / f"{topic}.v{version}.avsc"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf8")))


def to_avro(record: BaseModel, schema: dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    schemaless_writer(buf, parse_schema(schema), record.model_dump())
    return buf.getvalue()


def from_avro[M: BaseModel](data: bytes, schema: dict[str, Any], model: type[M]) -> M:
    return model.model_validate(schemaless_reader(io.BytesIO(data), parse_schema(schema)))
