# infra/k3s — the Kubernetes path

Kustomize manifests for the same images, probes and roles the compose stack uses: one
`Deployment` + `Service` per service, `StatefulSet`s for Postgres and Redpanda, one `Job` that
waits for Postgres, applies the migrations (dbmate), sets the role passwords and seeds the
dimensions. Readiness probes hit `/ready`, liveness `/health`. Containers run non-root with a
read-only root filesystem. Secrets come from `secrets.example.yaml` for a demo; a
`SealedSecret` placeholder shows the production shape.

**Exercised once on a single-node k3d cluster (k3s in Docker) on a laptop, 2026-09-23; not part
of CI.** What was run and what happened:

```sh
k3d cluster create qgate --servers 1 --agents 0 --wait
kubectl kustomize --load-restrictor LoadRestrictionsNone infra/k3s | kubectl apply -f -
#   26 objects; images pulled from ghcr.io/zakaria17amir/qgate-*:0.1.0-rc1 (~6 min on this link);
#   Job migrate: wait-for-postgres -> migrate -> roles -> seed-dims, Complete;
#   9 pods Running and Ready.
kubectl -n qgate port-forward svc/api 18000:8000 &
kubectl -n qgate port-forward svc/postgres 15432:5432 &
# load one golden into the cluster's Postgres, then through the api:
#   POST /triage         -> proposal after 2.0 s: PROPOSED WINDOW ST-19, 53 vehicles
#   POST .../approve     -> COMMITTED, plant ref HOLD-000001
k3d cluster delete qgate
```

Two things the exercise found and the manifests now carry: the migrate Job must wait for Postgres
(it exhausted its retries while the image was still pulling), and the dimensions must be seeded
before any service writes facts (the compose file gained the same `seed` one-shot).

## Files

| File | Purpose |
|---|---|
| `kustomization.yaml` | resources, image tags, ConfigMaps generated from `schemas/`, `knowledge/`, `db/migrations`, `db/set_role_passwords.sql` and `eval/cassettes` (replay mode) |
| `namespace.yaml` `config.yaml` | namespace `qgate`; non-secret settings as one ConfigMap |
| `secrets.example.yaml` | demo `Secret` — **replace before any real use** |
| `sealed-secret.example.yaml` | the same keys as a Bitnami `SealedSecret` (needs the controller + `kubeseal`) |
| `postgres.yaml` `redpanda.yaml` | StatefulSets with 5 Gi PVCs; single replica each |
| `migrate-job.yaml` | wait → dbmate → role passwords → dimension seed |
| `services.yaml` | ingest, detect, detect-worker, agent, api, mock-mes, console |
| `_gen.py` | generates all of the above (`uv run python infra/k3s/_gen.py`); bump `TAG` there |

## Known gaps (documented, not fixed)

- `--load-restrictor LoadRestrictionsNone` is needed because the ConfigMaps read files from the
  repo root; a packaged chart would copy them in.
- The console image bakes `VITE_API_BASE_URL=http://localhost:8000`; on a cluster, port-forward
  the api to 8000 or rebuild the image with the ingress URL.
- No Ingress, no TLS, no NetworkPolicy, no HPA; the agent is a single replica (its breaker and
  in-flight claims are per process).
- Observability (Prometheus, Grafana, Langfuse) and Prefect are compose-only.
