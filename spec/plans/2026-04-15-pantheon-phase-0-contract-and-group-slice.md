# Pantheon Phase 0 — Contract Docs + Group Slice Implementation Plan

> For Hermes: use subagent-driven-development discipline if this gets delegated. Keep the slice small, spec-grounded, and verified with uv.

Goal: turn the fresh scaffold into the first real Pantheon slice by locking the implementation contract docs, then implementing only SQLite bootstrap plus the first two CLI commands: `pantheon group init <name>` and `pantheon group list`.

Architecture: keep Pantheon as a thin local control plane with one importable package at `pantheon/`. Put repo metadata at root, binding contract docs in `spec/`, code in `pantheon/`, and tests in `tests/`. For this slice, persistence is a small SQLite bootstrap layer, the CLI is a thin edge, and no runtime execution logic is added. Use adjacent systems only as mechanical reference points, not as product blueprints.

Tech stack: Python 3.11+, uv, sqlite3 from stdlib, pytest, ruff, pyright, Typer/Rich deferred unless needed by the slice.

---

## Scope gate

This slice includes only:
- package-shape cleanup to match the agreed repo rule
- binding contract docs derived from the V1 brief
- SQLite bootstrap for the minimum V1 tables
- `pantheon group init <name>`
- `pantheon group list`
- automated tests for the new persistence and CLI behavior

This slice does not include:
- Hermes adapter execution
- runner/orchestrator loop behavior in code
- TUI implementation
- structured output parsing in code
- goal/task/run execution behavior beyond schema definition
- Textual, Rich, or Typer unless the command surface truly needs them now

---

## Target repo shape after this slice

Top level:
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `AGENTS.md`
- `spec/`
- `pantheon/`
- `tests/`

Package:
- `pantheon/__init__.py`
- `pantheon/cli.py`
- `pantheon/db.py`
- `pantheon/adapters.py`
- `pantheon/runner.py`
- `pantheon/tui.py`

Tests:
- `tests/test_cli.py`
- `tests/test_db.py`

Spec additions:
- `spec/SCHEMA.md`
- `spec/ADAPTERS.md`
- `spec/RUNNER.md`
- `spec/CLI_TUI.md`

Note: `pantheon/adapters.py`, `pantheon/runner.py`, and `pantheon/tui.py` may remain placeholder modules in this slice if needed only to lock package shape. Do not add fake behavior to them.

---

## Task 1: Normalize the early package shape

Objective: reshape the package so it matches the agreed Python repo structure before more code lands.

Files:
- Modify: `pantheon/cli.py`
- Create: `pantheon/db.py`
- Create: `pantheon/adapters.py`
- Create: `pantheon/runner.py`
- Create: `pantheon/tui.py`
- Test: none yet

Step 1: Create empty boundary modules

Create these files with docstrings only:

`pantheon/db.py`
```python
"""SQLite bootstrap and persistence helpers for Pantheon."""
```

`pantheon/adapters.py`
```python
"""Hermes adapter boundaries for Pantheon."""
```

`pantheon/runner.py`
```python
"""Runner loop boundaries for Pantheon."""
```

`pantheon/tui.py`
```python
"""Terminal UI entrypoints for Pantheon."""
```

Step 2: Keep `pantheon/cli.py` thin

For now it should remain a minimal shell that can later call into `db.py` and other modules.

Step 3: Verify imports still work

Run:
`UV_CACHE_DIR=.uv-cache uv run python -c "import pantheon, pantheon.cli, pantheon.db, pantheon.adapters, pantheon.runner, pantheon.tui"`

Expected: command exits 0 with no output.

Step 4: Commit

```bash
git add pantheon/
git commit -m "refactor: normalize early pantheon package shape"
```

---

## Task 2: Write `spec/SCHEMA.md`

Objective: turn the V1 brief’s table sketch into a binding schema contract for the first persistence slice.

Files:
- Create: `spec/SCHEMA.md`
- Reference: `spec/PANTHEON_V1_BRIEF.md`
- Reference: `spec/PANTHEON_DOCTRINE.md`

Step 1: Write the schema contract

The document should define:
- purpose of the SQLite database
- exact V1 tables:
  - groups
  - agents
  - goals
  - tasks
  - runs
  - events
- exact columns and intended types
- primary keys and foreign keys
- minimal required indexes
- invariants that must be enforced in SQL vs Python
- what is intentionally deferred

Include explicit notes such as:
- UUID/text IDs vs integer IDs choice
- timestamps stored in UTC ISO 8601 text or integer epoch, but one standard only
- `one active run per agent` is a future dispatch invariant and does not need to be fully enforced in this first CLI group slice unless the schema already needs support for it

Step 2: Review against V1 brief

Read `spec/PANTHEON_V1_BRIEF.md` and confirm there is no schema drift.

Step 3: Commit

```bash
git add spec/SCHEMA.md
git commit -m "docs: add pantheon schema contract"
```

---

## Task 3: Write `spec/ADAPTERS.md`

Objective: lock the Hermes adapter boundary before any runtime code appears.

Files:
- Create: `spec/ADAPTERS.md`
- Reference: `spec/PANTHEON_V1_BRIEF.md`
- Reference: `spec/PANTHEON_DOCTRINE.md`

Step 1: Write the adapter contract

The document should define:
- Pantheon owns orchestration state only
- Hermes adapter owns process invocation only
- required input shape for agent/task/run context
- streaming event categories
- final result fields
- rules the adapter must not break:
  - no direct Pantheon DB mutation
  - no inspection of Pantheon internals
  - must use agent-specific workspace and `HERMES_HOME`

Step 2: Keep V1 narrow

Do not define multiple adapter kinds, plugin registries, or transport abstractions beyond what V1 already needs.

Step 3: Commit

```bash
git add spec/ADAPTERS.md
git commit -m "docs: add pantheon adapter contract"
```

---

## Task 4: Write `spec/RUNNER.md`

Objective: isolate the runner loop semantics into one binding document.

Files:
- Create: `spec/RUNNER.md`
- Reference: `spec/PANTHEON_V1_BRIEF.md`

Step 1: Write the runner contract

The document should define:
- queued task selection order
- run creation semantics
- agent busy/idle state transitions
- event emission expectations
- lead-agent structured output handling boundary
- what happens on task failure
- what does and does not make a goal terminal

Step 2: Keep code out of it

No pseudocode framework sprawl. Just exact rules and state transitions.

Step 3: Commit

```bash
git add spec/RUNNER.md
git commit -m "docs: add pantheon runner contract"
```

---

## Task 5: Write `spec/CLI_TUI.md`

Objective: separate the operator surface contract from implementation.

Files:
- Create: `spec/CLI_TUI.md`
- Reference: `spec/PANTHEON_V1_BRIEF.md`

Step 1: Write the surface contract

The document should define:
- exact required V1 CLI commands
- the rule that the TUI is the primary surface and CLI is secondary
- exact required TUI screens and actions
- what can be inspection-only vs mutation-capable
- command output expectations for `group init` and `group list`

Step 2: Lock the first slice output shape

For the first slice, define simple deterministic CLI output such as:
- `group init` prints created group ID and name
- `group list` prints a newline-delimited or tabular view with stable columns

Step 3: Commit

```bash
git add spec/CLI_TUI.md
git commit -m "docs: add pantheon cli and tui contract"
```

---

## Task 6: Add dev dependencies and verification tooling

Objective: make the repo testable before persistence code lands.

Files:
- Modify: `pyproject.toml`
- Test: verification commands only

Step 1: Add minimal dev dependencies

Add only what this slice needs:
- `pytest`
- `ruff`
- `pyright`

If a CLI framework is needed for this slice, add exactly one. Otherwise use stdlib `argparse` for now.

Example shape:
```toml
[dependency-groups]
dev = [
  "pytest>=8.0",
  "ruff>=0.11",
  "pyright>=1.1",
]
```

Step 2: Sync environment

Run:
`UV_CACHE_DIR=.uv-cache uv sync --group dev`

Expected: environment resolves and installs cleanly.

Step 3: Smoke-check tooling

Run:
- `UV_CACHE_DIR=.uv-cache uv run pytest`
- `UV_CACHE_DIR=.uv-cache uv run ruff check .`
- `UV_CACHE_DIR=.uv-cache uv run pyright`

Expected: tests may be empty but commands must run successfully.

Step 4: Commit

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pantheon verification tooling"
```

---

## Task 7: Write failing DB bootstrap tests

Objective: define the first persistence behavior with tests before implementation.

Files:
- Create: `tests/test_db.py`
- Modify later: `pantheon/db.py`

Step 1: Write a failing test for database bootstrap

Test behaviors:
- creating a new database file initializes the required tables
- rerunning bootstrap is safe and idempotent

Example test:
```python
import sqlite3
from pathlib import Path

from pantheon.db import bootstrap_database


def test_bootstrap_database_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        connection.close()

    table_names = {row[0] for row in rows}
    assert {"groups", "agents", "goals", "tasks", "runs", "events"} <= table_names
```

Step 2: Add idempotency test

```python
def test_bootstrap_database_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    bootstrap_database(db_path)
    bootstrap_database(db_path)
```

Step 3: Run only the new DB tests

Run:
`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_db.py -v`

Expected: FAIL — `bootstrap_database` not defined yet.

Step 4: Commit

```bash
git add tests/test_db.py
git commit -m "test: define pantheon db bootstrap behavior"
```

---

## Task 8: Implement SQLite bootstrap in `pantheon/db.py`

Objective: add the smallest persistence layer that satisfies the contract and tests.

Files:
- Modify: `pantheon/db.py`
- Test: `tests/test_db.py`

Step 1: Implement `bootstrap_database`

Suggested minimal implementation shape:
```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # remaining tables...
)


def bootstrap_database(db_path: PathLike) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()
```

Step 2: Keep it minimal

Do not add an ORM. Do not add repository classes. Do not add generalized migration machinery.

Step 3: Run DB tests

Run:
`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_db.py -v`

Expected: PASS.

Step 4: Commit

```bash
git add pantheon/db.py tests/test_db.py
git commit -m "feat: add pantheon sqlite bootstrap"
```

---

## Task 9: Write failing CLI tests for group commands

Objective: define the command behavior before implementing it.

Files:
- Create: `tests/test_cli.py`
- Modify later: `pantheon/cli.py`
- Modify later: `pantheon/db.py`

Step 1: Decide CLI style

If the repo stays stdlib-only for now, test subprocess invocation through `uv run pantheon ...`.
If Typer is adopted for the CLI shell, test through its runner utilities.

Default recommendation for this slice: stdlib `argparse` plus subprocess tests.

Step 2: Write failing test for group creation

Behavior:
- command creates DB if needed
- command inserts a group row
- command prints deterministic confirmation

Example:
```python
import sqlite3
import subprocess
from pathlib import Path


def test_group_init_creates_group(tmp_path: Path) -> None:
    db_path = tmp_path / "pantheon.db"

    result = subprocess.run(
        [
            "uv",
            "run",
            "pantheon",
            "--db",
            str(db_path),
            "group",
            "init",
            "research",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "research" in result.stdout

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute("SELECT name FROM groups").fetchone()
    finally:
        connection.close()

    assert row == ("research",)
```

Step 3: Write failing test for group listing

Behavior:
- command prints all groups in deterministic order
- empty DB returns explicit empty-state output

Step 4: Run the CLI tests

Run:
`UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cli.py -v`

Expected: FAIL — commands not implemented yet.

Step 5: Commit

```bash
git add tests/test_cli.py
git commit -m "test: define pantheon group cli behavior"
```

---

## Task 10: Implement group creation and listing

Objective: add the first real operator commands without widening scope.

Files:
- Modify: `pantheon/cli.py`
- Modify: `pantheon/db.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_db.py`

Step 1: Add tiny DB helpers

Recommended functions:
- `connect_database(db_path)`
- `create_group(db_path, name)`
- `list_groups(db_path)`

Keep them in `pantheon/db.py` for now.

Step 2: Add a tiny CLI parser

Use `argparse` unless there is a real reason to introduce Typer now.

Recommended command shape:
- `pantheon --db /path/to/pantheon.db group init <name>`
- `pantheon --db /path/to/pantheon.db group list`

Step 3: Keep output deterministic

Examples:
- create: `created group <id> research`
- list header: `id\tname`
- empty state: `no groups`

Step 4: Run focused tests

Run:
- `UV_CACHE_DIR=.uv-cache uv run pytest tests/test_db.py tests/test_cli.py -v`

Expected: PASS.

Step 5: Commit

```bash
git add pantheon/cli.py pantheon/db.py tests/test_cli.py tests/test_db.py
git commit -m "feat: add pantheon group init and list commands"
```

---

## Task 11: Run the full verification stack

Objective: prove the slice is real and clean.

Files:
- Modify: none unless fixes are required

Step 1: Run tests

`UV_CACHE_DIR=.uv-cache uv run pytest`

Expected: PASS.

Step 2: Run Ruff

`UV_CACHE_DIR=.uv-cache uv run ruff check .`

Expected: PASS.

Step 3: Run Pyright

`UV_CACHE_DIR=.uv-cache uv run pyright`

Expected: PASS.

Step 4: Fix only what fails and rerun

Do not broaden the slice while cleaning verification failures.

Step 5: Commit

```bash
git add .
git commit -m "chore: verify pantheon phase 0 group slice"
```

---

## Acceptance criteria for this next step

The next step is complete when all of these are true:
- the repo shape matches the agreed one-package structure
- the binding docs exist:
  - `spec/SCHEMA.md`
  - `spec/ADAPTERS.md`
  - `spec/RUNNER.md`
  - `spec/CLI_TUI.md`
- `pantheon/db.py` can bootstrap the SQLite DB idempotently
- `pantheon group init <name>` creates a group in the DB
- `pantheon group list` lists saved groups deterministically
- tests pass under uv
- ruff passes
- pyright passes
- no adapter execution, runner logic, or TUI behavior has been implemented beyond placeholders

## Notes on judgment calls

- Use stdlib `sqlite3` for now. No ORM.
- Use stdlib `argparse` for now unless there is a strong reason to add Typer immediately.
- Keep IDs simple and deterministic in the contract. UUID strings are acceptable if chosen consistently.
- Keep timestamps in one format only across all tables.
- Do not let placeholder modules accumulate fake abstractions. If a module has no real work yet, keep it as a docstring and move on.
