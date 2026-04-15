# Pantheon

Pantheon is a local, terminal-first control plane for running a saved group of Hermes agents against a user-submitted goal.

It owns orchestration state, task dispatch, run supervision, live terminal visibility, and final inspection. Hermes remains the agent execution runtime.

## Status

Pantheon is in early development.

Current phase:
- locking implementation contracts
- building the first SQLite + CLI slice

The binding product contract lives in `spec/`.

## Current Scope

Pantheon V1 is being built as:
- local-first
- terminal-first
- SQLite-backed
- Hermes-only for runtime execution
- TUI-first, CLI-second

Core control-plane objects:
- groups
- agents
- goals
- tasks
- runs
- events

## Not Built Yet

Pantheon does not yet have:
- a working TUI
- SQLite control-plane implementation
- Hermes adapter execution
- runner/orchestrator behavior in code
- goal/task/run inspection beyond the current scaffold

## Local Setup

Requirements:
- Python 3.11+
- `uv`

Install dev dependencies:

```bash
UV_CACHE_DIR=.uv-cache uv sync --group dev
```

Run the current scaffold:

```bash
UV_CACHE_DIR=.uv-cache uv run pantheon
```

## Repository Layout

- `spec/` — binding product and implementation contracts
- `spec/plans/` — implementation and phase plans
- `pantheon/` — application code
- `tests/` — automated verification
- `docs/` — future product/operator documentation
- `tmp/` — local scratch/reference area; gitignored and not source of truth

## Read First

- `spec/PANTHEON_DOCTRINE.md`
- `spec/PANTHEON_V1_BRIEF.md`
- `spec/plans/2026-04-15-pantheon-phase-0-contract-and-group-slice.md`
