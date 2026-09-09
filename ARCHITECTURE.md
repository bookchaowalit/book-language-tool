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

## Recovery and compatibility

The source file remains the rebuild input and the IR format is versioned. A
digest mismatch stops execution. The safe rollback target for this baseline is
the previous source/artifact pair; no migration or external runtime state is
created.
