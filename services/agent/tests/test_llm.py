"""The cassette layer: record once, replay forever, never call a provider in replay."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from qgate_agent.llm import Ask, CassetteMissError, Mode
from qgate_core.pricing import Usage, cost_usd

pytestmark = pytest.mark.unit


class Verdict(BaseModel):
    station_id: str
    why: str


class FakeModel:
    """Stands in for the provider: returns a fixed structured answer and usage, counts calls."""

    calls = 0

    name = "fake"

    def invoke(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        FakeModel.calls += 1
        return schema(station_id="ST-19", why="torque measured here"), Usage(
            prompt_tokens=120, completion_tokens=20
        )


@pytest.fixture
def prompts(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    for pid in ("hypothesise", "p"):
        lines = ["---", f"id: {pid}", "version: 1", "---", "Vehicle {vin} {a}"]
        (d / f"{pid}.md").write_text("\n".join(lines), encoding="utf8")
    return d


def ask_in(mode: Mode, tmp_path: Path, prompts: Path) -> Ask:
    return Ask(
        mode=mode, cassette_dir=tmp_path / "cassettes", model=FakeModel(), prompts_dir=prompts
    )


def test_replay_miss_raises_and_never_calls_the_model(tmp_path: Path, prompts: Path) -> None:
    """Review Focus 3."""
    ask = ask_in("replay", tmp_path, prompts)
    FakeModel.calls = 0
    with pytest.raises(CassetteMissError):
        ask("hypothesise", "v1", {"vin": "SYN1"}, Verdict)
    assert FakeModel.calls == 0


def test_record_then_replay_round_trips_without_the_model(tmp_path: Path, prompts: Path) -> None:
    FakeModel.calls = 0
    recorded, usage = ask_in("record", tmp_path, prompts)(
        "hypothesise", "v1", {"vin": "SYN1", "a": 1}, Verdict
    )
    assert FakeModel.calls == 1 and usage.prompt_tokens == 120
    assert len(list((tmp_path / "cassettes").glob("*.json"))) == 1

    replayed, usage2 = ask_in("replay", tmp_path, prompts)(
        "hypothesise", "v1", {"vin": "SYN1", "a": 1}, Verdict
    )
    assert FakeModel.calls == 1 and replayed == recorded and usage2 == usage


def test_prompt_version_is_part_of_the_key(tmp_path: Path, prompts: Path) -> None:
    ask_in("record", tmp_path, prompts)("p", "v1", {"vin": "x", "a": 1}, Verdict)
    with pytest.raises(CassetteMissError):
        ask_in("replay", tmp_path, prompts)("p", "v2", {"vin": "x", "a": 1}, Verdict)


def test_cost_comes_from_a_labelled_price_table() -> None:
    usd = cost_usd("claude-haiku-4-5", Usage(prompt_tokens=1_000_000, completion_tokens=0))
    assert (
        usd is not None and 0.5 <= usd <= 2.0
    )  # order-of-magnitude sanity; the table is an assumption
    assert cost_usd("unknown-model", Usage(prompt_tokens=10, completion_tokens=10)) is None


def test_ollama_provider_points_at_the_configured_host() -> None:
    """Air-gapped profile: a native Ollama on the host, reached via host.docker.internal."""
    from qgate_agent.llm import LangChainModel

    m = LangChainModel("qwen2.5:7b", "ollama", None, base_url="http://host.docker.internal:11434")
    assert type(m._chat).__name__ == "ChatOllama"
    assert m._chat.base_url == "http://host.docker.internal:11434"
    assert m.name == "qwen2.5:7b"
