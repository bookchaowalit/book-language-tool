---
title: Book Language Tool Baseline Evidence
tags: [evidence, verification, compiler, reference-app]
created: 2026-09-06
updated: 2026-09-06
status: verified-local
---

# Baseline Evidence

## Scope

This record covers the local `compile-run-small-program` vertical slice only.
It does not claim a production release, hosted execution, IDE integration, or
untrusted-code safety certification.

## Reproducible checks

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m book_language_tool.cli check examples/hello.book
PYTHONPATH=src python3 -m book_language_tool.cli run examples/hello.book
```

Expected baseline result:

- all offline tests pass;
- `check` exits `0`;
- `run` prints `hello book language` and `42`;
- `examples/invalid.book` exits `3` with a syntax diagnostic;
- no network, credential, external process, or deployment action is required.

## Observed result — 2026-09-06

- `unittest`: 25 tests passed (incl. `tests/test_limits_and_validation.py`);
- `check examples/hello.book`: exit `0`;
- `run examples/hello.book`: printed `hello book language` and `42`;
- `check examples/invalid.book --json`: exit `3`, diagnostic code `P007`;
- the baseline used only the local Python runtime and repository files.

The commands are intentionally kept here as a reproducible evidence recipe;
the actual result should be refreshed after each implementation change.
