"""Thin helpers over confluent-kafka: topics, registry-backed Avro (de)serialisation, DLQ.

Partition counts and keys follow ADR-002. Consumers never auto-commit — the caller commits after
its side effect succeeded, which is what makes ingest at-least-once and the upsert idempotent.
"""

import base64
import json
from datetime import UTC, datetime
from typing import Any, cast

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, Producer
from confluent_kafka.admin import AdminClient
from confluent_kafka.cimpl import NewTopic
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from pydantic import BaseModel

from qgate_core.avro import load_schema
from qgate_core.models import TOPIC, Record, key_of
from qgate_core.settings import Settings

DLQ_TOPIC = "line.dlq"
PARTITIONS = {
    **{t: 6 for t in TOPIC.values() if t.startswith("line.")},
    **{t: 3 for t in TOPIC.values() if t.startswith("quality.")},
    DLQ_TOPIC: 1,
}


def ensure_topics(settings: Settings) -> None:
    """Create every topic with its designed partition count; existing topics are left alone."""
    admin = AdminClient({"bootstrap.servers": settings.kafka_bootstrap})
    futures = admin.create_topics([NewTopic(t, num_partitions=p) for t, p in PARTITIONS.items()])
    for f in futures.values():
        try:
            f.result()
        except KafkaException as e:
            if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise


def producer(settings: Settings) -> Producer:
    return Producer(
        {"bootstrap.servers": settings.kafka_bootstrap, "enable.idempotence": True, "linger.ms": 20}
    )


def consumer(settings: Settings, group: str, topics: list[str]) -> Consumer:
    c = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": group,
            "enable.auto.commit": False,
            "auto.offset.reset": "earliest",
        }
    )
    c.subscribe(topics)
    return c


def _registry(settings: Settings) -> SchemaRegistryClient:
    return SchemaRegistryClient({"url": settings.schema_registry_url})


def serializer(settings: Settings, topic: str) -> AvroSerializer:
    ser = AvroSerializer(
        _registry(settings),
        json.dumps(load_schema(topic)),
        to_dict=lambda rec, _ctx: rec.model_dump(),
    )
    return cast(AvroSerializer, ser)


def deserializer[M: BaseModel](settings: Settings, topic: str, model: type[M]) -> AvroDeserializer:
    des = AvroDeserializer(
        _registry(settings),
        json.dumps(load_schema(topic)),
        from_dict=lambda d, _ctx: model.model_validate(d),
    )
    return cast(AvroDeserializer, des)


_serializers: dict[str, AvroSerializer] = {}
_deserializers: dict[str, AvroDeserializer] = {}


def produce(settings: Settings, p: Producer, record: Record) -> Producer:
    """Serialise ``record`` for its topic and enqueue it keyed per ADR-002."""
    topic = TOPIC[type(record)]
    ser = _serializers.get(topic) or _serializers.setdefault(topic, serializer(settings, topic))
    p.produce(
        topic,
        key=key_of(record),
        value=ser(record, SerializationContext(topic, MessageField.VALUE)),
    )
    p.poll(0)
    return p


def poll(c: Consumer, timeout: float) -> Message | None:
    """Poll once; ``None`` on timeout. Broker-level errors raise; decode errors are the caller's."""
    msg = c.poll(timeout)
    if msg is None:
        return None
    if msg.error():
        raise KafkaException(msg.error())
    return msg


def decode[M: BaseModel](settings: Settings, msg: Message, model: type[M]) -> M:
    """Deserialise a Confluent-wire-format Avro payload into ``model`` (raises on bad bytes)."""
    topic = msg.topic() or ""
    des = _deserializers.get(topic) or _deserializers.setdefault(
        topic, deserializer(settings, topic, model)
    )
    return cast(M, des(msg.value(), SerializationContext(topic, MessageField.VALUE)))


def send_to_dlq(p: Producer, msg: Message, error: Exception) -> None:
    """Park an undecodable or invalid message with enough context to replay it by hand."""
    body: dict[str, Any] = {
        "topic": msg.topic(),
        "partition": msg.partition(),
        "offset": msg.offset(),
        "error": f"{type(error).__name__}: {error}",
        "raw_b64": base64.b64encode(msg.value() or b"").decode(),
        "failed_at": datetime.now(UTC).isoformat(),
    }
    p.produce(DLQ_TOPIC, key=msg.key(), value=json.dumps(body).encode())
    p.poll(0)
