# ADR-001: Synthetic data is the primary source; competition datasets are never committed

**Status:** Accepted · **Date:** 2026-09-21

## Context

Public manufacturing datasets that resemble a vehicle line (e.g. the Bosch Production Line Performance data) are Kaggle competition data whose rules commonly restrict redistribution. The evaluation needs specific, controllable defect scenarios — tool wear, shift steps, bad lots, a drifting test bench — with known ground truth, which no public dataset labels. The repository must clone and run for a stranger with one command.

## Decision

A seeded synthetic generator (`packages/qgate-generator`) is the primary and only committed data source. Every scenario declares its ground truth. An optional adapter reads a competition dataset from a local path the user supplies, behind a flag, and is not exercised in CI.

## Alternatives considered

- **Commit a competition dataset** — licence exposure; no ground truth for containment; reviewer cannot run without a Kaggle account.
- **Download at build time** — still redistribution in effect; flaky CI; same missing ground truth.
- **Public non-competition dataset (e.g. SECOM)** — no VIN/station/genealogy structure; would have to be synthesised around it anyway.

## Consequences

- Every metric in the README is over synthetic data and is labelled as such.
- The generator must be adversarial (confounders, correlated noise, bench faults) or every metric is trivially perfect; this is a stated risk with its own test.
- The adapter is a demonstration of "real data would plug in here", not a claim of validation on real data.
