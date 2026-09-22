"""After a load run: nothing may be left mid-flight (Phase 5 Review Focus 4), and the summary
must exist. Prints the numbers docs/latency.md quotes."""

import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

from qgate_core.auth import Role, mint

ROOT = Path(__file__).parents[1]


def main() -> int:
    env = {k: (v or "").split("#")[0].strip() for k, v in dotenv_values(ROOT / ".env").items()}
    api = httpx.Client(
        base_url="http://localhost:8000",
        headers={"Authorization": f"Bearer {mint('k6', Role.VIEWER, env['JWT_SECRET'])}"},
        timeout=30,
        follow_redirects=True,  # /metrics is a mounted app: 307 to /metrics/
    )
    m = json.loads((ROOT / "eval" / "load.json").read_text(encoding="utf8"))["metrics"]
    lines = api.get("/metrics").text.splitlines()
    failed = next((ln for ln in lines if 'outcome="FAILED"' in ln), "x 0").split()[-1]
    pending = next(ln for ln in lines if ln.startswith("gate_pending")).split()[-1]
    n = int(m["iterations"]["count"])
    for name in ("triage_to_proposal_ms", "approve_to_committed_ms"):
        v = m[name]
        print(
            f"{name:26s} n={n:4d}  p50={v['med']:.0f}  p95={v['p(95)']:.0f}  "
            f"p99={v['p(99)']:.0f}  max={v['max']:.0f} ms"
        )
    fails = m.get("iteration_failures", {}).get("count", 0)
    print(
        f"iterations={int(m['iterations']['count'])} failures={fails} "
        f"gate_pending_after={pending} failed_triages={failed}"
    )
    ok = float(failed) == 0 and fails < 5
    print("OK" if ok else "NOT OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
