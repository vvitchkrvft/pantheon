# Pantheon repo operating manual

Read these first:
1. `spec/PANTHEON_DOCTRINE.md`
2. `spec/PANTHEON_V1_BRIEF.md`

Rules:
- Pantheon is the control plane, not the runtime.
- Hermes is the only runtime in V1.
- Keep the adapter boundary strict.
- SQLite is the source of truth.
- TUI first, CLI second.
- No web UI, no multi-user system, no plugin platform.
- Use `uv`, not `pip`.
- Keep changes small, testable, and spec-grounded.

Initial repo shape:
- `spec/` holds the binding product contract.
- `pantheon/` holds implementation.
- `tests/` holds automated verification.
- `tmp/reference/` is reference material only, not source of truth.
