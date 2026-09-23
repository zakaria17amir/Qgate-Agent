"""Every relative link in the public Markdown must resolve (Phase 6 Review Focus 4).

Run by ``make lint``. Only local paths are checked; http(s) links are someone else's uptime.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
FILES = [
    ROOT / "README.md",
    ROOT / "RUNBOOK.md",
    *ROOT.glob("docs/**/*.md"),
    *ROOT.glob("*/README.md"),
]
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s#]+)(#[^)]*)?\)")


def main() -> int:
    bad = []
    for md in FILES:
        if ".venv" in md.parts or "node_modules" in md.parts:
            continue
        for target, _ in LINK.findall(md.read_text(encoding="utf8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                bad.append(f"{md.relative_to(ROOT)}: {target}")
    for b in bad:
        print("broken link:", b)
    print(f"{len(FILES)} files checked, {len(bad)} broken")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
