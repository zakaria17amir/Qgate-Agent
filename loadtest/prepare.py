"""Load one golden into the running stack and write the case the k6 script drives.

Run by ``make load``; needs ``.env`` (the same file compose used). The agent must be in replay
mode with the repo's cassettes mounted, or every iteration would bill the provider.
"""

import json
from pathlib import Path

from dotenv import dotenv_values

from qgate_core.auth import Role, mint
from qgate_eval.golden import Golden
from qgate_eval.runner import load_case

ROOT = Path(__file__).parents[1]


def main(golden_id: str = "drift-05") -> None:
    env = {k: (v or "").split("#")[0].strip() for k, v in dotenv_values(ROOT / ".env").items()}
    pg = (
        f"postgres://qgate_migrate:{env['POSTGRES_PASSWORD']}@localhost:"
        f"{env.get('POSTGRES_HOST_PORT') or 15432}/qgate"
    )
    g = Golden.load(ROOT / "eval" / "goldens" / f"{golden_id}.yaml")
    load_case(pg, g)
    case = {
        "golden": g.id,
        "vin": g.trigger.vin,
        "fault_codes": g.trigger.fault_codes,
        "token": mint("k6", Role.APPROVER, env["JWT_SECRET"]),
    }
    (ROOT / "loadtest" / "case.json").write_text(json.dumps(case, indent=1) + "\n", encoding="utf8")
    print(f"{g.id}: {g.trigger.vin} {g.trigger.fault_codes} loaded; loadtest/case.json written")


if __name__ == "__main__":
    main()
