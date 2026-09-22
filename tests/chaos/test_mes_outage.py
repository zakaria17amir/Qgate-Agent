"""Design §9.4: the plant system is unreachable while a commit is in flight."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from chaos.conftest import committed

pytestmark = pytest.mark.chaos


def test_outage_mid_commit_yields_exactly_one_hold(
    api: httpx.Client,
    mes: httpx.Client,
    toxiproxy: httpx.Client,
    triage_to_gate: Callable[[str], dict[str, Any]],
    wait: Callable[..., None],
) -> None:
    row = triage_to_gate("drift-03")
    cid = row["containment_id"]
    committed_before = committed(api)
    holds_before = mes.get("/_stats").json()["holds"]

    toxiproxy.post("/proxies/mock-mes", json={"enabled": False}).raise_for_status()
    try:
        api.post(f"/containments/{cid}/approve", json={}).raise_for_status()
        wait(  # five attempts with backoff, then parked
            lambda: api.get(f"/containments/{cid}").json()["state"] == "COMMIT_PENDING",
            timeout_s=60,
        )
    finally:
        toxiproxy.post("/proxies/mock-mes", json={"enabled": True}).raise_for_status()

    wait(  # breaker open 60 s + sweeper cadence 30 s
        lambda: api.get(f"/containments/{cid}").json()["state"] == "COMMITTED",
        timeout_s=150,
        every_s=5,
    )
    # exactly one hold per containment that reached COMMITTED meanwhile (the sweeper may also
    # finish rows left over from earlier runs), and this containment's hold is its own
    final = api.get(f"/containments/{cid}").json()
    assert mes.get("/_stats").json()["holds"] - holds_before == committed(api) - committed_before
    assert mes.get(f"/v1/holds/{final['mes_ref']}").json()["external_ref"] == cid
