# ruff: noqa: E501, S108  — a generator of manifests: long literal lines and /tmp mounts are the point
"""One-shot generator for the kustomize manifests (kept so a version bump is a re-run, not an edit
of seven Deployments by hand). Run: uv run python infra/k3s/_gen.py"""

from pathlib import Path
from typing import Any

import yaml

OUT = Path(__file__).parent
NS = "qgate"
TAG = "0.1.0-rc1"
IMG = "ghcr.io/zakaria17amir/qgate-"
PG = "postgres:16.4@sha256:e62fbf9d3e2b49816a32c400ed2dba83e3b361e6833e624024309c35d334b412"
RP = "redpandadata/redpanda:v24.2.7@sha256:82a69763bef8d8b55ea5a520fa1b38f993908ef68946819ca1aed43541824c48"
DBMATE = (
    "amacneil/dbmate:2.19@sha256:84043c7409dec5494d861c3c1779adbe28a41a283cf8103e6c08f7b829f5563d"
)


def dump(name: str, docs: list[dict[str, Any]]) -> None:
    text = "---\n".join(yaml.safe_dump(d, sort_keys=False, width=100) for d in docs)
    (OUT / name).write_text(text, encoding="utf8", newline="\n")


def secret_env(*names: str) -> list[dict[str, Any]]:
    return [
        {"name": n, "valueFrom": {"secretKeyRef": {"name": "qgate-secrets", "key": n}}}
        for n in names
    ]


def probe(path: str, **extra: Any) -> dict[str, Any]:
    return {
        "httpGet": {"path": path, "port": "http"},
        "periodSeconds": 10,
        "timeoutSeconds": 3,
        "failureThreshold": 6,
        **extra,
    }


def pg_url(role: str, name: str = "DATABASE_URL") -> dict[str, Any]:
    return {"name": name, "value": f"postgres://{role}:$(POSTGRES_PASSWORD)@postgres:5432/qgate"}


def deployment(
    name: str,
    image: str,
    port: int,
    env: list[dict[str, Any]] | None = None,
    args: list[str] | None = None,
    ready: str = "/ready",
    live: str = "/health",
    mounts: list[dict[str, Any]] | None = None,
    volumes: list[dict[str, Any]] | None = None,
    run_as: int = 10001,
    config: bool = True,
) -> list[dict[str, Any]]:
    container: dict[str, Any] = {
        "name": name,
        "image": image,
        "ports": [{"containerPort": port, "name": "http"}],
        "env": [{"name": "PORT", "value": str(port)}, *(env or [])],
        "readinessProbe": probe(ready, initialDelaySeconds=10),
        "livenessProbe": probe(live, initialDelaySeconds=20),
        "securityContext": {
            "readOnlyRootFilesystem": True,
            "allowPrivilegeEscalation": False,
            "runAsNonRoot": True,
            "runAsUser": run_as,
        },
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}, *(mounts or [])],
        "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"memory": "1Gi"}},
    }
    if config:
        container["envFrom"] = [{"configMapRef": {"name": "qgate-config"}}]
    if args is not None:
        container["args"] = args
    dep = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": {"app": name}},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [container],
                    "volumes": [{"name": "tmp", "emptyDir": {}}, *(volumes or [])],
                },
            },
        },
    }
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {
            "selector": {"app": name},
            "ports": [{"port": port, "targetPort": "http", "name": "http"}],
        },
    }
    return [dep, svc]


SCHEMAS = [{"name": "schemas", "mountPath": "/schemas", "readOnly": True}]
SCHEMAS_VOL = [{"name": "schemas", "configMap": {"name": "qgate-schemas"}}]
KNOWLEDGE = [{"name": "knowledge", "mountPath": "/knowledge", "readOnly": True}]
KNOWLEDGE_VOL = [{"name": "knowledge", "configMap": {"name": "qgate-knowledge"}}]


def main() -> None:
    dump("namespace.yaml", [{"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NS}}])
    dump(
        "config.yaml",
        [
            {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {"name": "qgate-config"},
                "data": {
                    "KAFKA_BOOTSTRAP": "redpanda:9092",
                    "SCHEMA_REGISTRY_URL": "http://redpanda:8081",
                    "QGATE_SCHEMAS_DIR": "/schemas",
                    "DETECT_BASE_URL": "http://detect:8002",
                    "API_BASE_URL": "http://api:8000",
                    "AGENT_BASE_URL": "http://agent:8001",
                    "MES_BASE_URL": "http://mock-mes:8003",
                    "FAULT_MAP_PATH": "/knowledge/fault_map.yaml",
                    "CASSETTE_DIR": "/cassettes",
                    "LLM_MODE": "replay",
                    "LLM_PROVIDER": "anthropic",
                    "LLM_MODEL": "claude-haiku-4-5",
                    "APPROVAL_TIMEOUT_S": "1800",
                    "CORS_ORIGINS": "http://localhost:8080,http://localhost:4173",
                    "PYTHONUNBUFFERED": "1",
                },
            }
        ],
    )
    keys = ("POSTGRES_PASSWORD", "JWT_SECRET", "MES_API_KEY", "LLM_API_KEY")
    dump(
        "secrets.example.yaml",
        [
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": "qgate-secrets"},
                "type": "Opaque",
                "stringData": {
                    "POSTGRES_PASSWORD": "change-me",
                    "JWT_SECRET": "dev-only-change-me-please-use-32-bytes",
                    "MES_API_KEY": "dev-mes-key",
                    "LLM_API_KEY": "",
                },
            }
        ],
    )
    dump(
        "sealed-secret.example.yaml",
        [
            {
                "apiVersion": "bitnami.com/v1alpha1",
                "kind": "SealedSecret",
                "metadata": {"name": "qgate-secrets", "namespace": NS},
                "spec": {
                    "encryptedData": {k: "<kubeseal output>" for k in keys},
                    "template": {
                        "metadata": {"name": "qgate-secrets", "namespace": NS},
                        "type": "Opaque",
                    },
                },
            }
        ],
    )
    pvc = [
        {
            "metadata": {"name": "data"},
            "spec": {
                "accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": "5Gi"}},
            },
        }
    ]
    dump(
        "postgres.yaml",
        [
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "postgres"},
                "spec": {
                    "clusterIP": "None",
                    "selector": {"app": "postgres"},
                    "ports": [{"port": 5432, "name": "pg"}],
                },
            },
            {
                "apiVersion": "apps/v1",
                "kind": "StatefulSet",
                "metadata": {"name": "postgres"},
                "spec": {
                    "serviceName": "postgres",
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "postgres"}},
                    "template": {
                        "metadata": {"labels": {"app": "postgres"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "postgres",
                                    "image": PG,
                                    "ports": [{"containerPort": 5432, "name": "pg"}],
                                    "env": [
                                        {"name": "POSTGRES_DB", "value": "qgate"},
                                        {"name": "POSTGRES_USER", "value": "qgate_migrate"},
                                        {
                                            "name": "PGDATA",
                                            "value": "/var/lib/postgresql/data/pgdata",
                                        },
                                        *secret_env("POSTGRES_PASSWORD"),
                                    ],
                                    "readinessProbe": {
                                        "exec": {
                                            "command": [
                                                "pg_isready",
                                                "-U",
                                                "qgate_migrate",
                                                "-d",
                                                "qgate",
                                            ]
                                        },
                                        "periodSeconds": 5,
                                    },
                                    "volumeMounts": [
                                        {"name": "data", "mountPath": "/var/lib/postgresql/data"}
                                    ],
                                    "resources": {
                                        "requests": {"cpu": "250m", "memory": "512Mi"},
                                        "limits": {"memory": "2Gi"},
                                    },
                                }
                            ]
                        },
                    },
                    "volumeClaimTemplates": pvc,
                },
            },
        ],
    )
    dump(
        "redpanda.yaml",
        [
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": "redpanda"},
                "spec": {
                    "clusterIP": "None",
                    "selector": {"app": "redpanda"},
                    "ports": [
                        {"port": 9092, "name": "kafka"},
                        {"port": 8081, "name": "registry"},
                        {"port": 9644, "name": "admin"},
                    ],
                },
            },
            {
                "apiVersion": "apps/v1",
                "kind": "StatefulSet",
                "metadata": {"name": "redpanda"},
                "spec": {
                    "serviceName": "redpanda",
                    "replicas": 1,
                    "selector": {"matchLabels": {"app": "redpanda"}},
                    "template": {
                        "metadata": {"labels": {"app": "redpanda"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "redpanda",
                                    "image": RP,
                                    "args": [
                                        "redpanda", "start", "--smp", "1", "--memory", "1G", "--overprovisioned",
                                        "--kafka-addr", "internal://0.0.0.0:9092",
                                        "--advertise-kafka-addr", "internal://redpanda:9092",
                                        "--schema-registry-addr", "0.0.0.0:8081",
                                    ],
                                    "ports": [
                                        {"containerPort": 9092, "name": "kafka"},
                                        {"containerPort": 8081, "name": "registry"},
                                        {"containerPort": 9644, "name": "admin"},
                                    ],
                                    "readinessProbe": {
                                        "httpGet": {"path": "/v1/status/ready", "port": "admin"},
                                        "periodSeconds": 5,
                                        "initialDelaySeconds": 10,
                                    },
                                    "volumeMounts": [{"name": "data", "mountPath": "/var/lib/redpanda/data"}],
                                    "resources": {
                                        "requests": {"cpu": "500m", "memory": "1Gi"},
                                        "limits": {"memory": "2Gi"},
                                    },
                                }
                            ]
                        },
                    },
                    "volumeClaimTemplates": pvc,
                },
            },
        ],
    )  # fmt: skip
    roles_cmd = (
        "psql -h postgres -U qgate_migrate -d qgate -v ON_ERROR_STOP=1 "
        '-v pw="$POSTGRES_PASSWORD" -f /db/set_role_passwords.sql'
    )
    dump(
        "migrate-job.yaml",
        [
            {
                "apiVersion": "batch/v1",
                "kind": "Job",
                "metadata": {"name": "migrate"},
                "spec": {
                    "backoffLimit": 20,
                    "template": {
                        "spec": {
                            "restartPolicy": "OnFailure",
                            "initContainers": [
                                {   # the database image may still be pulling when this Job starts
                                    "name": "wait-for-postgres",
                                    "image": PG,
                                    "command": ["sh", "-c",
                                                "until pg_isready -h postgres -U qgate_migrate -d qgate; do sleep 3; done"],
                                },
                                {
                                    "name": "migrate",
                                    "image": DBMATE,
                                    "args": ["up"],
                                    "env": [
                                        *secret_env("POSTGRES_PASSWORD"),
                                        {
                                            "name": "DATABASE_URL",
                                            "value": "postgres://qgate_migrate:$(POSTGRES_PASSWORD)@postgres:5432/qgate?sslmode=disable",
                                        },
                                        {"name": "DBMATE_MIGRATIONS_DIR", "value": "/db/migrations"},
                                        {"name": "DBMATE_NO_DUMP_SCHEMA", "value": "true"},
                                    ],
                                    "volumeMounts": [{"name": "migrations", "mountPath": "/db/migrations", "readOnly": True}],
                                },
                                {
                                    "name": "roles",
                                    "image": PG,
                                    "env": [
                                        *secret_env("POSTGRES_PASSWORD"),
                                        {"name": "PGPASSWORD", "value": "$(POSTGRES_PASSWORD)"},
                                    ],
                                    "command": ["sh", "-c", roles_cmd],
                                    "volumeMounts": [{"name": "roles", "mountPath": "/db", "readOnly": True}],
                                },
                            ],
                            "containers": [
                                {   # stations, characteristics, shifts, benches from line.yaml (idempotent)
                                    "name": "seed-dims",
                                    "image": f"{IMG}gen:{TAG}",
                                    "args": ["seed-dims", "--scenarios-dir", "/workspace/scenarios"],
                                    "env": [*secret_env("POSTGRES_PASSWORD"), pg_url("ingest_rw")],
                                    "securityContext": {"runAsNonRoot": True, "runAsUser": 10001},
                                }
                            ],
                            "volumes": [
                                {"name": "migrations", "configMap": {"name": "qgate-migrations"}},
                                {"name": "roles", "configMap": {"name": "qgate-roles-sql"}},
                            ],
                        }
                    },
                },
            }
        ],
    )  # fmt: skip

    services: list[dict[str, Any]] = []
    services += deployment(
        "ingest",
        f"{IMG}ingest:{TAG}",
        8010,
        env=[*secret_env("POSTGRES_PASSWORD"), pg_url("ingest_rw")],
        mounts=SCHEMAS,
        volumes=SCHEMAS_VOL,
    )
    services += deployment(
        "detect",
        f"{IMG}detect:{TAG}",
        8002,
        args=["api"],
        env=[*secret_env("POSTGRES_PASSWORD"), pg_url("detect_ro")],
        mounts=SCHEMAS,
        volumes=SCHEMAS_VOL,
    )
    services += deployment(
        "detect-worker",
        f"{IMG}detect:{TAG}",
        8012,
        args=["worker"],
        env=[*secret_env("POSTGRES_PASSWORD"), pg_url("detect_ro")],
        mounts=SCHEMAS,
        volumes=SCHEMAS_VOL,
    )
    services += deployment(
        "agent",
        f"{IMG}agent:{TAG}",
        8001,
        env=[
            *secret_env("POSTGRES_PASSWORD", "JWT_SECRET", "MES_API_KEY", "LLM_API_KEY"),
            pg_url("agent_ro", "DATABASE_URL_AGENT_RO"),
            pg_url("checkpoint_rw", "DATABASE_URL_CHECKPOINT_RW"),
        ],
        mounts=[
            *SCHEMAS,
            *KNOWLEDGE,
            {"name": "cassettes", "mountPath": "/cassettes", "readOnly": True},
        ],
        volumes=[
            *SCHEMAS_VOL,
            *KNOWLEDGE_VOL,
            {"name": "cassettes", "configMap": {"name": "qgate-cassettes"}},
        ],
    )
    services += deployment(
        "api",
        f"{IMG}api:{TAG}",
        8000,
        env=[*secret_env("POSTGRES_PASSWORD", "JWT_SECRET"), pg_url("api_rw")],
        mounts=SCHEMAS,
        volumes=SCHEMAS_VOL,
    )
    services += deployment(
        "mock-mes", f"{IMG}mock-mes:{TAG}", 8003, env=secret_env("MES_API_KEY"), ready="/health"
    )
    services += deployment(
        "console",
        f"{IMG}console:{TAG}",
        8080,
        ready="/",
        live="/",
        run_as=101,
        config=False,
        mounts=[
            {"name": "nginx-cache", "mountPath": "/var/cache/nginx"},
            {"name": "nginx-run", "mountPath": "/var/run"},
        ],
        volumes=[{"name": "nginx-cache", "emptyDir": {}}, {"name": "nginx-run", "emptyDir": {}}],
    )
    dump("services.yaml", services)  # fmt: skip

    schemas = [
        "line.build.events",
        "line.measurements",
        "line.eol.results",
        "quality.alerts",
        "quality.containment",
    ]
    migrations = [
        "0000_schema",
        "0001_dims",
        "0002_facts",
        "0003_containment",
        "0004_roles",
        "0005_evidence",
    ]
    dump(
        "kustomization.yaml",
        [
            {
                "apiVersion": "kustomize.config.k8s.io/v1beta1",
                "kind": "Kustomization",
                "namespace": NS,
                "resources": ["namespace.yaml", "config.yaml", "secrets.example.yaml", "postgres.yaml",
                              "redpanda.yaml", "migrate-job.yaml", "services.yaml"],
                "configMapGenerator": [
                    {"name": "qgate-schemas", "files": [f"../../schemas/{s}.v1.avsc" for s in schemas]},
                    {"name": "qgate-knowledge", "files": ["../../knowledge/fault_map.yaml"]},
                    {"name": "qgate-migrations", "files": [f"../../db/migrations/{m}.sql" for m in migrations]},
                    {"name": "qgate-roles-sql", "files": ["../../db/set_role_passwords.sql"]},
                    # replay mode answers from the recorded cassettes (364 KB); live mode needs LLM_API_KEY
                    {"name": "qgate-cassettes", "files": sorted(f"../../eval/cassettes/{p.name}"
                                                                for p in (OUT.parents[1] / "eval" / "cassettes").glob("*.json"))},
                ],
                "generatorOptions": {"disableNameSuffixHash": True},
                "images": [{"name": f"{IMG}{s}", "newTag": TAG}
                           for s in ("ingest", "detect", "agent", "api", "mock-mes", "console", "gen")],
            }
        ],
    )  # fmt: skip


if __name__ == "__main__":
    main()
