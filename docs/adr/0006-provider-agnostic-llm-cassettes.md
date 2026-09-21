# ADR-006: Provider-agnostic LLM with cassette record/replay

**Status:** Accepted · **Date:** 2026-09-21

## Context

The agent needs a model in exactly two nodes (ADR-004). Model vendors change pricing and model ids monthly; an air-gapped plant may allow no external calls at all. CI must be deterministic and free, but the published numbers must come from a real model.

## Decision

The agent obtains its model through `langchain.chat_models.init_chat_model(LLM_MODEL, model_provider=LLM_PROVIDER, temperature=0)`; provider and model are environment, not code. Every call passes through a cassette layer keyed by `hash(prompt_id, prompt_version, inputs)` with three modes: `live` (call, record nothing), `record` (call and write `eval/cassettes/<key>.json`), `replay` (read; a missing cassette is a hard failure, never a live call). CI runs `replay`; the nightly flow runs `live` and publishes.

## Alternatives considered

- **One vendor SDK directly** — simplest code, but switching vendors touches every node, and the Ollama profile becomes a fork.
- **Mock the model in tests** — mocks assert what we wrote, not what the model said; cassettes are real responses frozen in time.
- **Live model in CI** — non-deterministic, costs money per push, leaks the key into more places.

## Consequences

- Changing a prompt changes its `version`, which invalidates its cassettes on purpose; re-recording is a deliberate, reviewed commit.
- Cassettes contain only synthetic VINs and generated text; they are safe to commit and are excluded from Docker build contexts.
- Cost per triage is computed from `response_metadata` usage against a small pricing table that is labelled as an assumption.
- Structured output quality differs by provider; the eval numbers name the provider and model they were produced with.
