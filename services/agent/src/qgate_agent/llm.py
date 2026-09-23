"""The only door to a language model, and the cassette layer in front of it (ADR-006).

``Ask`` renders a versioned prompt, asks the model for a structured answer, and depending on
``mode`` records or replays that answer keyed by ``(prompt id, version, inputs)``. In ``replay``
a missing cassette is an error — CI never talks to a provider by accident.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from qgate_core.pricing import Usage

Mode = Literal["live", "record", "replay", "template"]  # template: no model at all
PROMPTS = Path(__file__).parent / "prompts"


class CassetteMissError(LookupError):
    """Replay asked for a prompt+inputs that were never recorded."""


class NoModelError(RuntimeError):
    """Template mode: the caller supplies a deterministic answer instead (a fresh clone has no
    API key and no cassettes for its own line; the tools still decide, only the prose is canned)."""


class StructuredModel(Protocol):
    name: str

    def invoke(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]: ...


class LangChainModel:
    """Any provider ``init_chat_model`` knows, at temperature 0, forced into a Pydantic schema."""

    def __init__(
        self, model: str, provider: str, api_key: str | None, base_url: str | None = None
    ) -> None:
        self.name = model
        kwargs: dict[str, Any] = {"temperature": 0}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:  # a local model server (the air-gapped profile's Ollama)
            kwargs["base_url"] = base_url
        self._chat = init_chat_model(model, model_provider=provider, **kwargs)

    def invoke(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        result = self._chat.with_structured_output(schema, include_raw=True).invoke(prompt)
        raw, parsed = result["raw"], result["parsed"]
        meta = getattr(raw, "usage_metadata", None) or {}
        usage = Usage(int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0)))
        if not isinstance(parsed, schema):
            raise ValueError(
                f"model did not return a {schema.__name__}: {result.get('parsing_error')}"
            )
        return parsed, usage


class Prompt(BaseModel):
    id: str
    version: str
    template: str

    def render(self, **inputs: Any) -> str:
        return self.template.format(**inputs)


def load_prompt(prompt_id: str, prompts_dir: Path = PROMPTS) -> Prompt:
    """``prompts/<id>.md``: YAML front matter (id, version) then the template body."""
    text = (prompts_dir / f"{prompt_id}.md").read_text(encoding="utf8")
    _, meta, body = text.split("---", 2)
    head = yaml.safe_load(meta)
    return Prompt(id=head["id"], version=str(head["version"]), template=body.strip())


class NoModelConfigured:
    """Stands in for the provider client when the mode never calls one (replay, template): a
    fresh clone must start without an API key."""

    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel, Usage]:
        raise NoModelError("no model configured for this mode")


class Ask:
    def __init__(
        self, mode: Mode, cassette_dir: Path, model: StructuredModel, prompts_dir: Path = PROMPTS
    ) -> None:
        self.mode, self.dir, self.model, self.prompts = mode, cassette_dir, model, prompts_dir

    def __call__[S: BaseModel](
        self, prompt_id: str, version: str, inputs: dict[str, Any], schema: type[S]
    ) -> tuple[S, Usage]:
        if self.mode == "template":
            raise NoModelError(prompt_id)
        key = self.dir / f"{_key(prompt_id, version, inputs)}.json"
        if self.mode == "replay":
            if not key.exists():
                raise CassetteMissError(f"{prompt_id} v{version}: no cassette {key.name}")
            saved = json.loads(key.read_text(encoding="utf8"))
            return schema.model_validate(saved["output"]), Usage(**saved["usage"])
        prompt = load_prompt(prompt_id, self.prompts).render(**inputs)
        answer, usage = self.model.invoke(prompt, schema)
        if self.mode == "record":
            self.dir.mkdir(parents=True, exist_ok=True)
            body = {
                "prompt_id": prompt_id,
                "version": version,
                "model": self.model.name,
                "inputs": inputs,
                "output": answer.model_dump(mode="json"),
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                },
            }
            # LF and a trailing newline regardless of host OS: cassettes are committed files
            with key.open("w", encoding="utf8", newline="\n") as f:
                f.write(json.dumps(body, indent=1, sort_keys=True, default=str) + "\n")
        if not isinstance(answer, schema):
            raise TypeError(f"model returned {type(answer).__name__}, expected {schema.__name__}")
        return answer, usage


def _key(prompt_id: str, version: str, inputs: dict[str, Any]) -> str:
    canonical = json.dumps([prompt_id, version, inputs], sort_keys=True, default=str)
    return f"{prompt_id}-{version}-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
