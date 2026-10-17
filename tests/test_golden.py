"""Golden-file tests: each ``.book`` program has a checked-in expected result.

Set ``UPDATE_GOLDEN=1`` to regenerate the ``.expected.json`` files after an
intentional change, then review the diff.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import unittest
from pathlib import Path

from book_language_tool.cli import main

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "golden"
PROGRAMS = sorted((ROOT / "examples").glob("*.book")) + sorted(
    GOLDEN_DIR.glob("*.book")
)


def _run(program: Path) -> dict:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
        exit_code = main(["run", str(program), "--json"])
    payload = json.loads(stdout.getvalue())
    payload.pop("source", None)  # absolute path differs per checkout
    return {"exit_code": exit_code, **payload}


class GoldenProgramTests(unittest.TestCase):
    def test_programs_match_expected_results(self) -> None:
        self.assertGreaterEqual(len(PROGRAMS), 5)
        for program in PROGRAMS:
            expected_path = (
                GOLDEN_DIR / f"{program.parent.name}__{program.stem}.expected.json"
            )
            actual = _run(program)
            if os.environ.get("UPDATE_GOLDEN") == "1":
                expected_path.write_text(
                    json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
            with self.subTest(program=program.name):
                self.assertTrue(
                    expected_path.exists(),
                    f"missing {expected_path.name}; run with UPDATE_GOLDEN=1",
                )
                expected = json.loads(expected_path.read_text(encoding="utf-8"))
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
