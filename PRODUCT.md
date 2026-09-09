---
title: Book Language Tool Product Brief
tags: [product, software, developer-tool, compiler]
created: 2026-09-06
updated: 2026-09-06
status: baseline-implemented
---

# Product Brief

## Outcome

A developer can write a small `.book` source file, validate it, compile it to
a stable intermediate representation, and run it locally with clear output or
actionable diagnostics.

## Vertical-slice acceptance

| ID | Acceptance | Evidence path |
|---|---|---|
| `deterministic-build` | The same source produces the same artifact and digest. | `tests/test_language_tool.py` |
| `useful-diagnostics` | Syntax and semantic failures expose stable code and source location. | `tests/test_language_tool.py` |
| `safe-execution-boundary` | Runtime executes only the Book instruction set and fails closed on malformed artifacts. | `src/book_language_tool/core.py` |
| `reversible-release` | The artifact format is versioned and digest-checked before execution. | `src/book_language_tool/core.py` |

## Decision boundary

This is an educational/reference tool, not a production compiler. Adding a
new language feature requires a fixture, parser/compiler behavior, runtime
behavior, and regression test. Adding external execution, network access, a
package manager, or a hosted service requires a new architecture decision and
security review.
