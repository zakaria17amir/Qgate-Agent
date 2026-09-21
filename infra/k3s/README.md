# k3s

Documented deployment path, **not CI-tested**. Same images as compose; kustomize manifests mapping each service to a `Deployment` (Postgres and Redpanda to `StatefulSet`s), `/health` → liveness, `/ready` → readiness, secrets via `SealedSecret` placeholders.

Exercised once on a single-node k3s VM in Phase 5. The README says exactly that and nothing more.
