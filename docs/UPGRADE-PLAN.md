# Upgrade Plan

**Current state: 7/10** — small, readable compiler/VM with stable
diagnostics, resource bounds and CI; language surface is still minimal and
the CLI cannot execute a saved IR artifact.

## Backlog

### P0
- (none open)

### P1
- Add `book-lang exec <artifact.json>` so compiled IR can be run (the VM
  already validates digest + operands); cover tampered-file cases.
- VM runtime diagnostics all report `1:1`; carry source line/column in IR
  (e.g. optional `loc` per instruction) so R00x points at the source.
- Golden-file tests: `examples/*.book` → expected stdout/diagnostics JSON.

### P2
- Language growth in small steps: comparison operators, `if`, then bounded
  `while` (the instruction limit already caps loops).
- `mypy --strict src` in CI.

## Done in this pass (2026-09-30)
- Crash fixes (Python tracebacks instead of diagnostics): Unicode digits
  like `²` (`int()` ValueError), numeric literals over 4,300 digits,
  deeply nested parentheses/unary minus (`RecursionError`).
- Resource bounds: 64-bit integers (`L004`/`R006`, overflow checked before
  multiplying), 64 KiB strings (`L005`/`R007`), nesting depth 100 (`P008`).
- VM validates re-signed artifacts: `CONST` operand type/range and
  `LOAD`/`STORE` identifiers (`R004`).
- Unknown string escape no longer cascades into a bogus `L002`.
- New `tests/test_limits_and_validation.py` (17 tests; 8 → 25 total).
- CI workflow; ARCHITECTURE documents bounds and division semantics.
