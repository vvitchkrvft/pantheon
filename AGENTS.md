# Pantheon repo operating manual

Read these first:
1. `spec/PANTHEON_DOCTRINE.md`
2. `spec/PANTHEON_V1_BRIEF.md`
3. `spec/plans/2026-04-15-pantheon-phase-0-contract-and-group-slice.md`

## Critical Rules

- Pantheon is the control plane; Hermes is the agent execution runtime.
- Hermes is the only agent execution runtime in V1.
- Keep the adapter boundary strict.
- SQLite is the source of truth.
- TUI first, CLI second.
- No web UI, no multi-user system, no plugin platform.
- Do not add runtime behavior that crosses the control-plane boundary.
- Do not define Pantheon through reference products; adjacent systems are mechanics references only.
- Do not add `src/` layout.
- Do not add root-level script soup.
- Do not put binding implementation contracts in `docs/`; use `spec/`.
- Do not add new dependencies without updating `pyproject.toml` and `uv.lock`.
- Do not commit unless explicitly instructed.

## Commands

Use `uv`, not `pip`.
Use `uv run ...`, not raw `python3`, for repo work.

Primary commands:
- Sync dev environment:
  - `UV_CACHE_DIR=.uv-cache uv sync --group dev`
- Run Pantheon scaffold:
  - `UV_CACHE_DIR=.uv-cache uv run pantheon`
- Run tests:
  - `UV_CACHE_DIR=.uv-cache uv run pytest`
- Run lint:
  - `UV_CACHE_DIR=.uv-cache uv run ruff check .`
- Run type check:
  - `UV_CACHE_DIR=.uv-cache uv run pyright`

## Verification After Edits

After meaningful code or contract changes:
1. `UV_CACHE_DIR=.uv-cache uv run pytest`
2. `UV_CACHE_DIR=.uv-cache uv run ruff check .`
3. `UV_CACHE_DIR=.uv-cache uv run pyright`

If `pyproject.toml` changes:
- rerun `UV_CACHE_DIR=.uv-cache uv sync --group dev`

## Repo Structure

- `spec/` holds binding product and implementation contracts.
- `spec/plans/` holds implementation and phase plans.
- `pantheon/` holds implementation.
- `tests/` holds automated verification.
- `docs/` is reserved for actual product/operator documentation.
- `tmp/` is local scratch/reference material, gitignored, and not source of truth.

## Code Conventions

- Keep changes small, testable, and spec-grounded.
- Prefer a clean one-package repo shape under `pantheon/`.
- Keep the CLI thin and scriptable.
- Keep future TUI code presentation-only; do not move orchestration policy into the UI layer.
- Prefer stdlib `sqlite3` for early persistence slices.
- Avoid speculative abstractions.
- Avoid junk-drawer modules like `utils/`, `helpers/`, `common/`, or `services/` unless a boundary is real and named precisely.
- Let file/module names follow product boundaries: db, adapters, runner, tui, groups, goals, tasks, runs, events.

## Git / Commit Conventions

- Only commit when explicitly instructed.
- Keep commit messages honest and scope-specific.
- Do not use “reboot” framing unless explicitly instructed.
- Treat the current Pantheon work as the first real build.

## Environment Notes

- Pantheon targets Python 3.11+.
- Match Hermes on Python floor; do not introduce a lower Python target.
- The repo’s managed environment is currently resolved by `uv` and should be treated as canonical.
