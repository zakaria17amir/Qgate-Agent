"""Supply chain (design §12): every image we pull is pinned by digest, so a re-tagged upstream
cannot change what runs. Dependabot's docker ecosystem bumps the digests."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).parents[3]
PINNED = re.compile(r"^[\w./-]+(:[\w.-]+)?@sha256:[0-9a-f]{64}$")
OURS = "ghcr.io/zakaria17amir/qgate-"  # built here, tagged :dev; not pulled


def _images() -> list[tuple[str, str]]:
    found = []
    for line in (ROOT / "docker-compose.yml").read_text(encoding="utf8").splitlines():
        if m := re.match(r"\s*image:\s*(\S+)", line):
            found.append(("docker-compose.yml", m.group(1)))
    for df in ROOT.glob("**/Dockerfile"):
        if ".venv" in df.parts or "node_modules" in df.parts:
            continue
        for line in df.read_text(encoding="utf8").splitlines():
            if m := re.match(r"FROM\s+(?:--platform=\S+\s+)?(\S+)", line):
                ref = m.group(1)
                if ref not in {"build", "test", "runtime"}:  # stage names
                    found.append((str(df.relative_to(ROOT)), ref))
    return found


def test_every_pulled_image_is_pinned_by_digest() -> None:
    images = _images()
    assert len(images) >= 15
    unpinned = [
        (f, ref)
        for f, ref in images
        if not ref.startswith(OURS) and "${" not in ref and not PINNED.match(ref)
    ]
    assert unpinned == [], unpinned
