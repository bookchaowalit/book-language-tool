"""`book-lang exec` for saved IR artifacts and source locations in runtime diagnostics."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from book_language_tool.cli import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE, main
from book_language_tool.core import VM, canonical_json, compile_source, run_source


def cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


def resign(artifact: dict) -> dict:
    payload = {
        key: value for key, value in artifact.items() if key != "artifact_sha256"
    }
    return {
        **payload,
        "artifact_sha256": hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest(),
    }


class ExecCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.artifact_path = Path(self.tmp.name) / "hello.ir.json"
        code, _, _ = cli(
            "compile",
            str(ROOT / "examples" / "hello.book"),
            "--out",
            str(self.artifact_path),
        )
        self.assertEqual(code, EXIT_OK)

    def write(self, text: str) -> str:
        path = Path(self.tmp.name) / "edited.ir.json"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def test_exec_runs_saved_artifact_like_run(self) -> None:
        code, out, _ = cli("exec", str(self.artifact_path))
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(out.splitlines(), ["hello book language", "42"])
        code, out, _ = cli("exec", str(self.artifact_path), "--json")
        payload = json.loads(out)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["output"], ["hello book language", "42"])
        _, run_out, _ = cli("run", str(ROOT / "examples" / "hello.book"), "--json")
        self.assertEqual(
            payload["artifact_sha256"], json.loads(run_out)["artifact_sha256"]
        )

    def test_tampered_artifact_is_rejected(self) -> None:
        artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        artifact["instructions"][0]["arg"] = "tampered"
        code, out, _ = cli("exec", self.write(json.dumps(artifact)), "--json")
        self.assertEqual(code, EXIT_RUNTIME)
        self.assertEqual(
            json.loads(out)["diagnostics"][0]["message"],
            "artifact digest does not match its contents",
        )

    def test_resigned_artifact_with_bad_loc_is_rejected(self) -> None:
        artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        for bad in ([0, 1], [1], "1:1", [True, 1], [1, 2, 3]):
            with self.subTest(loc=bad):
                artifact["instructions"][0]["loc"] = bad
                code, out, _ = cli(
                    "exec", self.write(json.dumps(resign(artifact))), "--json"
                )
                self.assertEqual(code, EXIT_RUNTIME)
                self.assertIn("loc", json.loads(out)["diagnostics"][0]["message"])

    def test_invalid_json_and_non_object_are_diagnostics(self) -> None:
        for text in ("{not json", "[]", "null", "[" * 100_000):
            with self.subTest(text=text[:10]):
                code, out, _ = cli("exec", self.write(text), "--json")
                self.assertEqual(code, EXIT_RUNTIME)
                self.assertEqual(json.loads(out)["diagnostics"][0]["code"], "R004")

    def test_artifact_level_errors_have_no_source_position(self) -> None:
        artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        artifact["instructions"][0]["arg"] = "tampered"
        path = self.write(json.dumps(artifact))
        code, out, _ = cli("exec", path, "--json")
        row = json.loads(out)["diagnostics"][0]
        self.assertEqual(code, EXIT_RUNTIME)
        self.assertEqual(
            (row["line"], row["column"], row["end_column"]), (None, None, None)
        )
        # Text output omits the position instead of inventing 1:1.
        code, _, err = cli("exec", path)
        self.assertEqual(code, EXIT_RUNTIME)
        self.assertEqual(
            err.strip(), f"{path}: R004 artifact digest does not match its contents"
        )
        code, _, err = cli("exec", self.write("{not json"))
        self.assertNotIn(":1:1:", err)
        self.assertIn(": R004 artifact is not valid JSON", err)

    def test_missing_file_is_usage_error(self) -> None:
        code, _, err = cli("exec", str(Path(self.tmp.name) / "absent.json"))
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("cannot read", err)


class RuntimeLocationTests(unittest.TestCase):
    def test_division_by_zero_points_at_operator(self) -> None:
        result = run_source('let a = 1;\nlet b = 0;\nprint("x");\nprint(a / b);\n')
        [diagnostic] = result.diagnostics
        self.assertEqual(
            (diagnostic.code, diagnostic.line, diagnostic.column), ("R002", 4, 9)
        )

    def test_type_error_points_at_operator(self) -> None:
        [diagnostic] = run_source('print(1);\nprint("a" * 2);').diagnostics
        self.assertEqual(
            (diagnostic.code, diagnostic.line, diagnostic.column), ("R003", 2, 11)
        )

    def test_unary_type_error_points_at_minus(self) -> None:
        [diagnostic] = run_source('let s = "x";\n  print(-s);').diagnostics
        self.assertEqual(
            (diagnostic.code, diagnostic.line, diagnostic.column), ("R003", 2, 9)
        )

    def test_every_non_halt_instruction_has_loc(self) -> None:
        artifact = compile_source("let a = 2;\nprint(-a + 3 * a);").artifact
        assert artifact is not None
        for instruction in artifact["instructions"]:
            if instruction["op"] != "HALT":
                self.assertIn("loc", instruction)

    def test_artifacts_without_loc_still_run(self) -> None:
        artifact = compile_source("print(1 / 0);").artifact
        assert artifact is not None
        stripped = resign(
            {
                **artifact,
                "instructions": [
                    {k: v for k, v in i.items() if k != "loc"}
                    for i in artifact["instructions"]
                ],
            }
        )
        _, diagnostics = VM().run(stripped)
        self.assertEqual(
            (diagnostics[0].code, diagnostics[0].line, diagnostics[0].column),
            ("R002", None, None),
        )
        row = diagnostics[0].as_dict()
        self.assertEqual(
            (row["line"], row["column"], row["end_column"]), (None, None, None)
        )


if __name__ == "__main__":
    unittest.main()
