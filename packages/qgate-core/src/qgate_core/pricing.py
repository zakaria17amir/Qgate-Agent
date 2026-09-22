"""USD per million tokens, by model. **An assumption**: copied from public price pages on the
date noted; not fetched live. Used only to report cost per triage, never to make decisions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


# model -> (input $/M tokens, output $/M tokens); read 2026-09-22
PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}


def cost_usd(model: str, usage: Usage) -> float | None:
    """None when the model is not in the table — better than a made-up number."""
    if model not in PRICES:
        return None
    inp, out = PRICES[model]
    return round((usage.prompt_tokens * inp + usage.completion_tokens * out) / 1_000_000, 6)
