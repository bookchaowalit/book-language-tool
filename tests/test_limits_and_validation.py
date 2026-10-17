#!/usr/bin/env python3
"""Resource bounds, hostile-input handling and IR artifact validation."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book_language_tool.core import (
    INT_MAX,
    MAX_NESTING_DEPTH,
    MAX_STRING_CHARS,
    VM,
    canonical_json,
    compile_source,
    run_source,
)


def codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def signed_artifact(instructions: list[dict]) -> dict:
    payload = {
        "format": "book-language-tool.ir.v1",
        "source_sha256": "0" * 64,
        "instructions": instructions,
    }
    artifact = dict(payload)
    artifact["artifact_sha256"] = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return artifact


class LexerTests(unittest.TestCase):
    def test_non_ascii_digits_are_diagnostics_not_crashes(self) -> None:
        for source in ("print(²);", "print(٣);", "let x٣ = 1;"):
            with self.subTest(source=source):
                self.assertEqual(codes(compile_source(source)), ["L001"])

    def test_integer_literal_out_of_range(self) -> None:
        self.assertEqual(codes(compile_source(f"print({INT_MAX + 1});")), ["L004"])
        self.assertEqual(codes(compile_source("print(" + "9" * 5000 + ");")), ["L004"])
        self.assertEqual(run_source(f"print({INT_MAX});").output, [str(INT_MAX)])

    def test_string_literal_too_long(self) -> None:
        source = 'print("' + "a" * (MAX_STRING_CHARS + 1) + '");'
        self.assertEqual(codes(compile_source(source)), ["L005"])

    def test_string_escapes_and_errors(self) -> None:
        self.assertEqual(run_source('print("a\\tb\\"c");').output, ['a\tb"c'])
        self.assertEqual(codes(compile_source('print("a\\q");')), ["L003"])
        self.assertEqual(codes(compile_source('print("open);')), ["L002"])

    def test_comments_are_ignored(self) -> None:
        self.assertEqual(run_source("# note\nprint(1); # trailing\n").output, ["1"])

    def test_lone_cr_ends_a_line(self) -> None:
        # A CR-only file used to be one line, so a comment swallowed the rest.
        self.assertEqual(run_source("# note\rprint(1);\rprint(2);").output, ["1", "2"])
        result = compile_source("print(1);\rprint(x);")
        self.assertEqual(
            [(d.code, d.line, d.column) for d in result.diagnostics], [("S001", 2, 7)]
        )
        crlf = compile_source("print(1);\r\nprint(x);")
        self.assertEqual([(d.line, d.column) for d in crlf.diagnostics], [(2, 7)])
        self.assertEqual(codes(compile_source('print("a\rb");'))[0], "L002")


class ParserTests(unittest.TestCase):
    def test_deep_nesting_is_bounded(self) -> None:
        depth = MAX_NESTING_DEPTH + 50
        result = compile_source("print(" + "(" * depth + "1" + ")" * depth + ");")
        self.assertIn("P008", codes(result))
        unary = compile_source("print(" + "-" * 5000 + "1);")
        self.assertIn("P008", codes(unary))

    def test_reasonable_nesting_still_works(self) -> None:
        self.assertEqual(
            run_source("print(" + "(" * 50 + "7" + ")" * 50 + ");").output, ["7"]
        )
        self.assertEqual(run_source("print(--3);").output, ["3"])

    def test_recovers_after_error_and_reports_each_statement(self) -> None:
        result = compile_source("let = 1;\nprint(2;\nprint(3);\n")
        self.assertEqual(codes(result), ["P002", "P006"])
        self.assertEqual([d.line for d in result.diagnostics], [1, 2])


class RuntimeBoundsTests(unittest.TestCase):
    def test_multiplication_overflow(self) -> None:
        source = "let a = 3037000500;\nlet b = a * a;\nprint(b);\n"
        self.assertEqual(codes(run_source(source)), ["R006"])

    def test_repeated_squaring_cannot_exhaust_memory(self) -> None:
        lines = (
            ["let v0 = 2;"]
            + [f"let v{i} = v{i - 1} * v{i - 1};" for i in range(1, 40)]
            + ["print(v39);"]
        )
        self.assertEqual(codes(run_source("\n".join(lines))), ["R006"])

    def test_addition_and_subtraction_overflow(self) -> None:
        self.assertEqual(codes(run_source(f"print({INT_MAX} + 1);")), ["R006"])
        self.assertEqual(codes(run_source(f"print(-{INT_MAX} - 2);")), ["R006"])
        self.assertEqual(
            run_source(f"print(-{INT_MAX} - 1);").output, [str(-INT_MAX - 1)]
        )

    def test_string_doubling_is_bounded(self) -> None:
        lines = (
            ['let s0 = "xxxxxxxx";']
            + [f"let s{i} = s{i - 1} + s{i - 1};" for i in range(1, 20)]
            + ["print(s19);"]
        )
        self.assertEqual(codes(run_source("\n".join(lines))), ["R007"])

    def test_division_semantics(self) -> None:
        self.assertEqual(run_source("print(7 / 2);").output, ["3"])
        self.assertEqual(codes(run_source("print(1 / 0);")), ["R002"])

    def test_type_errors(self) -> None:
        self.assertEqual(codes(run_source('print("a" * 2);')), ["R003"])
        self.assertEqual(codes(run_source('print(-"a");')), ["R003"])
        self.assertEqual(run_source('print("a" + "b");').output, ["ab"])


class ArtifactValidationTests(unittest.TestCase):
    def test_resigned_artifact_with_bad_operands_is_rejected(self) -> None:
        bad_programs = [
            [{"op": "CONST", "arg": True}, {"op": "PRINT"}, {"op": "HALT"}],
            [{"op": "CONST", "arg": 1.5}, {"op": "PRINT"}, {"op": "HALT"}],
            [{"op": "CONST", "arg": [1]}, {"op": "PRINT"}, {"op": "HALT"}],
            [{"op": "CONST", "arg": INT_MAX + 1}, {"op": "PRINT"}, {"op": "HALT"}],
            [
                {"op": "CONST", "arg": 1},
                {"op": "STORE", "arg": "not an ident"},
                {"op": "HALT"},
            ],
            [{"op": "LOAD"}, {"op": "PRINT"}, {"op": "HALT"}],
        ]
        for instructions in bad_programs:
            with self.subTest(instructions=instructions):
                output, diagnostics = VM().run(signed_artifact(instructions))
                self.assertEqual(output, [])
                self.assertEqual([d.code for d in diagnostics], ["R004"])

    def test_valid_resigned_artifact_runs(self) -> None:
        output, diagnostics = VM().run(
            signed_artifact(
                [
                    {"op": "CONST", "arg": 5},
                    {"op": "STORE", "arg": "x"},
                    {"op": "LOAD", "arg": "x"},
                    {"op": "PRINT"},
                    {"op": "HALT"},
                ]
            )
        )
        self.assertEqual((output, diagnostics), (["5"], []))

    def test_instruction_limit(self) -> None:
        instructions = [{"op": "CONST", "arg": 1}, {"op": "PRINT"}] * 6000 + [
            {"op": "HALT"}
        ]
        _, diagnostics = VM().run(signed_artifact(instructions))
        self.assertEqual([d.code for d in diagnostics], ["R005"])


if __name__ == "__main__":
    unittest.main()
