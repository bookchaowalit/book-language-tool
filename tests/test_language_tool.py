#!/usr/bin/env python3
"""Offline tests for the Book Language Tool vertical slice."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book_language_tool.core import VM, canonical_json, compile_source, run_source  # noqa: E402


class LanguageToolTests(unittest.TestCase):
    def test_compile_and_run(self) -> None:
        source = (ROOT / "tests" / "fixtures" / "hello.book").read_text(
            encoding="utf-8"
        )
        compiled = compile_source(source)
        self.assertEqual(compiled.diagnostics, [])
        self.assertIsNotNone(compiled.artifact)
        assert compiled.artifact is not None
        self.assertEqual(compiled.artifact["format"], "book-language-tool.ir.v1")

        result = run_source(source)
        self.assertEqual(result.diagnostics, [])
        self.assertEqual(result.output, ["hello book language", "42"])

    def test_artifact_is_deterministic(self) -> None:
        source = "let x = (2 + 3) * 4;\nprint(x);\n"
        first = compile_source(source).artifact
        second = compile_source(source).artifact
        self.assertEqual(first, second)
        self.assertEqual(canonical_json(first), canonical_json(second))

    def test_syntax_diagnostic_has_location(self) -> None:
        result = compile_source("print(1 + );\n")
        self.assertIsNone(result.artifact)
        self.assertEqual(result.diagnostics[0].code, "P007")
        self.assertEqual(result.diagnostics[0].line, 1)
        self.assertGreaterEqual(result.diagnostics[0].column, 9)

    def test_undefined_variable_is_rejected(self) -> None:
        result = compile_source("let known = 1;\nprint(missing);\n")
        self.assertIsNone(result.artifact)
        self.assertEqual(result.diagnostics[0].code, "S001")
        self.assertEqual(result.diagnostics[0].line, 2)

    def test_tampered_artifact_is_rejected(self) -> None:
        artifact = compile_source("print(1);\n").artifact
        self.assertIsNotNone(artifact)
        assert artifact is not None
        artifact["instructions"][0]["arg"] = 2
        output, diagnostics = VM().run(artifact)
        self.assertEqual(output, [])
        self.assertEqual(diagnostics[0].code, "R004")

    def test_runtime_error_is_fail_closed(self) -> None:
        result = run_source("print(4 / 0);\n")
        self.assertEqual(result.output, [])
        self.assertEqual(result.diagnostics[0].code, "R002")

    def test_cli_json_run(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        command = [
            sys.executable,
            "-m",
            "book_language_tool.cli",
            "run",
            str(ROOT / "examples" / "hello.book"),
            "--json",
        ]
        completed = subprocess.run(
            command, cwd=ROOT, env=env, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["output"], ["hello book language", "42"])

    def test_cli_json_diagnostic(self) -> None:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        command = [
            sys.executable,
            "-m",
            "book_language_tool.cli",
            "check",
            str(ROOT / "examples" / "invalid.book"),
            "--json",
        ]
        completed = subprocess.run(
            command, cwd=ROOT, env=env, text=True, capture_output=True, check=False
        )
        self.assertEqual(completed.returncode, 3)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["diagnostics"][0]["code"], "P007")


if __name__ == "__main__":
    unittest.main()
