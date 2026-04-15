# Pantheon

Pantheon is a local, terminal-first control plane for running a saved group of Hermes agents against a user-submitted goal.

It owns orchestration state, task dispatch, run supervision, live terminal visibility, and final inspection. Hermes remains the agent execution runtime.

## Status

Pantheon is in early development.

Current phase:
- first real execution slice is implemented
- control-plane persistence, dispatch, and status inspection are working against a real Hermes adapter path
- ACP is now the primary adapter transport, with Hermes CLI query mode retained as fallback when ACP is unusable before prompt dispatch
- structured lead control payloads and goal completion from lead judgments are now implemented in the control plane

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

## Implemented So Far

The current CLI supports:
- `pantheon group init <name>`
- `pantheon group list`
- `pantheon agent add --group <group-name-or-id> --name <name> --role <lead|worker> --hermes-home <path> --workdir <path> [--profile-name ...] [--model-override ...] [--provider-override ...]`
- `pantheon goal submit "<goal text>" --group <group-name-or-id>`
- `pantheon start <goal-id>`
- `pantheon status <goal-id>`

The repo also includes:
- SQLite bootstrap for the V1 core tables
- agent registry scaffolding with one-lead-per-group enforcement
- goal submission scaffolding that creates a queued goal and queued root task assigned to the group lead
- a first runner slice that persists run, task, agent, and event state transitions
- an ACP-backed Hermes adapter path that prefers `hermes acp` and falls back to `hermes chat -q ... -Q --source tool` when ACP is unusable before prompt dispatch
- richer adapter result normalization including structured `session_id` and `usage_json` when ACP provides them
- structured lead-output handling for `task_proposal` and `completion_judgment`
- same-pass dispatch of newly-ready child tasks when their parent completes
- run-row inspection in `pantheon status <goal-id>`

## Not Built Yet

Pantheon does not yet have:
- a working TUI
- full ACP-native progress/thinking/tool-event mapping into Pantheon's event model
- broader goal/task/run inspection surfaces beyond the current CLI status output
- deeper operator controls around retry/cancel/inspection workflows

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

Example current flow:

```bash
UV_CACHE_DIR=.uv-cache uv run pantheon group init research
UV_CACHE_DIR=.uv-cache uv run pantheon agent add --group research --name lead-1 --role lead --hermes-home /tmp/hermes-home --workdir /tmp/workdir
UV_CACHE_DIR=.uv-cache uv run pantheon goal submit "Ship the first Pantheon slice" --group research
UV_CACHE_DIR=.uv-cache uv run pantheon start <goal-id>
UV_CACHE_DIR=.uv-cache uv run pantheon status <goal-id>
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
- `spec/ADAPTERS.md`
- `spec/RUNNER.md`
- `spec/CLI_TUI.md`
- `spec/plans/2026-04-15-pantheon-phase-0-contract-and-group-slice.md`
