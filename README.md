---
title: Book Language Tool
aliases: [Reference Developer Tool, Book Lang]
tags: [software, developer-tool, compiler, interpreter, reference-app]
created: 2026-09-06
updated: 2026-09-06
description: Deterministic local-first compiler/interpreter vertical slice for the Software Program Factory.
status: baseline-implemented
related: [systems/architecture/reference-app-workbench, systems/architecture/software-program-factory]
---

# Book Language Tool

Book Language Tool is the first implemented reference app from the Software
Program Factory. It proves the `programming-language-tool` category (#7) with a
small source language, deterministic JSON IR, structured diagnostics, and a
closed local VM.

## Purpose and boundary

The user is a developer who needs a tiny, repeatable source → compile → run
path for learning and regression fixtures. The implementation is intentionally
small enough to inspect end-to-end.

Included:

- `let` declarations for integers and strings;
- integer arithmetic (`+`, `-`, `*`, `/`) and string concatenation;
- `print(expression);` statements;
- line/column diagnostics with stable error codes;
- deterministic `book-language-tool.ir.v1` artifacts and SHA-256 digests;
- an interpreter that executes only the tool's own instruction set.

Excluded:

- arbitrary Python, shell, or OS process execution;
- package registries, IDE plugins, hosted execution, and untrusted-user service;
- external dependencies, credentials, network access, and deployment.

## Quick start

No dependency installation is required for the baseline:

```bash
PYTHONPATH=src python3 -m book_language_tool.cli check examples/hello.book
PYTHONPATH=src python3 -m book_language_tool.cli compile examples/hello.book --out /tmp/hello.ir.json
PYTHONPATH=src python3 -m book_language_tool.cli exec /tmp/hello.ir.json
PYTHONPATH=src python3 -m book_language_tool.cli run examples/hello.book
```

Expected run output:

```text
hello book language
42
```

Machine-readable output is available with `--json`. Exit codes are:

| Code | Meaning |
|---:|---|
| `0` | success |
| `2` | usage or file I/O error |
| `3` | lexical, syntax, or semantic diagnostic |
| `4` | runtime/artifact diagnostic |

## Development loop

```bash
make check
make test
make demo
make typecheck   # needs mypy; strict settings live in pyproject.toml
```

The source is split into lexer/parser/compiler/VM logic in
`src/book_language_tool/core.py` and a thin CLI in
`src/book_language_tool/cli.py`. Tests are offline `unittest` cases and cover
happy path, deterministic artifacts, syntax/semantic errors, runtime failure,
JSON CLI behavior, resource bounds (64-bit integers, string size, nesting
depth, instruction count), re-signed artifact operand validation, `exec` of
saved/tampered artifacts, runtime source locations, and golden files
(`tests/golden/*.expected.json`, regenerate with `UPDATE_GOLDEN=1 make test`
and review the diff). See
[ARCHITECTURE.md](ARCHITECTURE.md#resource-bounds) for the limits. CI
(`.github/workflows/ci.yml`) runs ruff, `mypy --strict` (pinned),
`make check`, `make test` and `make demo` on every push.

## Role and step handoff

This repository implements the `build` slice of
`reference-developer-tool`'s `compile-run-small-program` flow. The parent
workbench remains the source for the full role × 14-step plan. This repository
does not claim completion of release, operation, or production evidence until
those steps have their own reviewed records.

See [ARCHITECTURE.md](ARCHITECTURE.md), [PRODUCT.md](PRODUCT.md), and
[evidence/BASELINE.md](evidence/BASELINE.md) for the current boundary and
verification record.
