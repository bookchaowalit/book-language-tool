---
title: Book Language Tool Architecture
tags: [architecture, compiler, interpreter, developer-tool]
created: 2026-09-06
updated: 2026-09-06
status: baseline-implemented
---

# Architecture

```text
.book source
    → Lexer (tokens + source diagnostics)
    → Parser (AST + syntax diagnostics)
    → Compiler (versioned JSON IR + semantic diagnostics)
    → VM (own instruction set only)
    → output or structured runtime diagnostic
```

## Contracts

- Source is UTF-8 text with one statement per terminated line/semicolon.
- Artifacts use `book-language-tool.ir.v1`.
- Artifact JSON is canonicalized with sorted keys and compact separators.
- `artifact_sha256` hashes the artifact payload without the digest field.
- Runtime verifies the digest before executing instructions.
- The VM has no instruction for shell, Python, filesystem, network, or process
  execution.
- The digest proves integrity, not origin, so the VM also validates operands:
  `CONST` must be a bounded integer (not bool/float) or string, and
  `LOAD`/`STORE` must name an identifier (`R004` otherwise).
- Instructions carry an optional `loc: [line, column]` (compiler emits it for
  every instruction except `HALT`); runtime diagnostics (`R001`–`R007`) report
  that source position. Artifacts without `loc` stay valid; their runtime
  errors, like artifact-level errors (format, digest, operands, invalid
  JSON), have no source position: JSON diagnostics carry `line`, `column`
  and `end_column` as `null` and text output prints `file: CODE message`
  without a fake `1:1`. A malformed `loc` is rejected with `R004`.
- `book-lang exec <artifact.json>` runs a saved artifact through the same
  validation (8 MiB file limit, invalid JSON → `R004`, exit code 4).

## Resource bounds

| Bound | Limit | Diagnostic |
|---|---|---|
| Integer literals and results | signed 64-bit (`-2^63 .. 2^63-1`) | `L004` literal, `R006` overflow |
| String literals and concatenation | 65,536 characters | `L005` literal, `R007` result |
| Expression nesting (parentheses / unary `-`) | 100 levels | `P008` |
| Executed instructions | 10,000 | `R005` |

Identifiers and numbers are ASCII-only; other characters (e.g. `²`, `٣`) are
`L001`. Integer `/` uses floor division (`7 / 2` → `3`, `-7 / 2` → `-4`).

## Recovery and compatibility

The source file remains the rebuild input and the IR format is versioned. A
digest mismatch stops execution. The safe rollback target for this baseline is
the previous source/artifact pair; no migration or external runtime state is
created.
