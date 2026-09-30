# Upgrade Plan

**Current state: 8/10** (pass 3: 7.5 -> 8) — small, readable compiler/VM with stable
diagnostics, resource bounds, source-located runtime errors, `exec` for saved
IR, golden-file tests and CI; language surface is still minimal.

## Backlog

### P0
- (none open)

### P1
- Language growth, first step: comparison operators (`<`, `==`, ...)
  producing integers 0/1, with lexer/parser/VM tests and a golden program.

### P2
- Then `if`, then bounded `while` (the instruction limit already caps
  loops); add jump operand validation (`R004`) for re-signed artifacts.

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

## Done in this pass (pass 2)
- `book-lang exec <artifact.json|->`: runs saved IR with digest/operand
  validation, 8 MiB size cap, invalid/deeply nested JSON → `R004` (exit 4),
  missing file → exit 2. CI compiles and execs the example after install.
- IR instructions carry optional `loc: [line, column]`; runtime diagnostics
  now point at the failing operator/statement instead of `1:1`; malformed
  `loc` in re-signed artifacts is rejected; loc-less artifacts still run.
- Golden-file tests (`tests/test_golden.py`, `tests/golden/`) for examples
  plus runtime/semantic/arithmetic programs; `UPDATE_GOLDEN=1` regenerates.
- Tests 25 → 36.

## Done in this pass (pass 3)
- Diagnostics without a source position (artifact format/digest/operand
  errors, invalid JSON, runtime errors in loc-less artifacts) no longer
  claim `1:1`: `Diagnostic.line/column/end_column` are optional, JSON emits
  `null`, text output prints `file: CODE message`. Source diagnostics and
  golden files are unchanged.
- `mypy --strict` clean (fixed 5 findings in `cli.py`: untyped `list`/`dict`,
  `_read_source` label is always `str`); `[tool.mypy]` config, `make
  typecheck`, and a pinned CI step (`mypy==2.3.1`).
- Tests 36 -> 37 (JSON nulls + text output for tampered/invalid artifacts;
  loc-less runtime error now asserts `None`). ruff 0.15.8/0.16.9 clean.
