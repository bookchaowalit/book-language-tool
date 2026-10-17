"""Command-line interface for the Book Language Tool."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import (
    VM,
    Diagnostic,
    canonical_json,
    compile_source,
    diagnostic_rows,
    run_source,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_DIAGNOSTIC = 3
EXIT_RUNTIME = 4

# A compiled artifact for the 10,000-instruction limit is well under 8 MiB;
# refuse larger files before parsing them.
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="book-lang",
        description="Compile, check, and run the deterministic Book language.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "compile", "run"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("source", help="source file path, or '-' for stdin")
        command_parser.add_argument(
            "--json", action="store_true", help="emit machine-readable JSON"
        )
        if command == "compile":
            command_parser.add_argument(
                "--out",
                type=Path,
                help="write the deterministic IR artifact to this path",
            )
    exec_parser = subparsers.add_parser(
        "exec", help="run a compiled IR artifact (JSON)"
    )
    exec_parser.add_argument("artifact", help="artifact file path, or '-' for stdin")
    exec_parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    return parser


def _load_artifact(text: str) -> tuple[object, list[Diagnostic]]:
    if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        return None, [
            Diagnostic("R004", f"artifact exceeds {MAX_ARTIFACT_BYTES} bytes")
        ]
    try:
        return json.loads(text), []
    except (json.JSONDecodeError, RecursionError):
        return None, [Diagnostic("R004", "artifact is not valid JSON")]


def _exec(args: argparse.Namespace, text: str, label: str) -> int:
    artifact, diagnostics = _load_artifact(text)
    output: list[str] = []
    if not diagnostics:
        output, diagnostics = VM().run(artifact)  # type: ignore[arg-type]
    if diagnostics:
        payload = {
            "status": "error",
            "command": "exec",
            "artifact": label,
            "diagnostics": diagnostic_rows(diagnostics),
        }
        if args.json:
            _emit(payload, True)
        else:
            _print_diagnostics(label, diagnostics)
        return EXIT_RUNTIME
    payload = {
        "status": "ok",
        "command": "exec",
        "artifact": label,
        "artifact_sha256": artifact["artifact_sha256"],  # type: ignore[index]
        "output": output,
    }
    if args.json:
        _emit(payload, True)
    else:
        for line in output:
            print(line)
        if not output:
            print("OK: program produced no output")
    return EXIT_OK


def _read_source(source_path: str) -> tuple[str | None, str]:
    """Return ``(text, label)``, or ``(None, error message)`` when unreadable."""
    if source_path == "-":
        return sys.stdin.read(), "<stdin>"
    path = Path(source_path)
    try:
        return path.read_text(encoding="utf-8"), str(path)
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read {path}: {exc}"


def _print_diagnostics(source_label: str, diagnostics: list[Diagnostic]) -> None:
    for diagnostic in diagnostics:
        position = (
            f"{diagnostic.line}:{diagnostic.column}:" if diagnostic.has_location else ""
        )
        print(
            f"{source_label}:{position} {diagnostic.code} {diagnostic.message}",
            file=sys.stderr,
        )


def _emit(value: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print(value["message"])


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source, source_label = _read_source(
        args.artifact if args.command == "exec" else args.source
    )
    if source is None:
        payload = {"status": "error", "command": args.command, "message": source_label}
        if args.json:
            _emit(payload, True)
        else:
            print(source_label, file=sys.stderr)
        return EXIT_USAGE

    if args.command == "exec":
        return _exec(args, source, source_label)

    if args.command == "run":
        result = run_source(source)
        if result.diagnostics:
            payload = {
                "status": "error",
                "command": "run",
                "source": source_label,
                "diagnostics": diagnostic_rows(result.diagnostics),
            }
            if args.json:
                _emit(payload, True)
            else:
                _print_diagnostics(source_label, result.diagnostics)
            return EXIT_RUNTIME if result.artifact else EXIT_DIAGNOSTIC
        payload = {
            "status": "ok",
            "command": "run",
            "source": source_label,
            "artifact_sha256": result.artifact["artifact_sha256"]
            if result.artifact
            else None,
            "output": result.output,
        }
        if args.json:
            _emit(payload, True)
        else:
            for line in result.output:
                print(line)
            if not result.output:
                print("OK: program produced no output")
        return EXIT_OK

    compiled = compile_source(source)
    if compiled.diagnostics or compiled.artifact is None:
        payload = {
            "status": "error",
            "command": args.command,
            "source": source_label,
            "diagnostics": diagnostic_rows(compiled.diagnostics),
        }
        if args.json:
            _emit(payload, True)
        else:
            _print_diagnostics(source_label, compiled.diagnostics)
        return EXIT_DIAGNOSTIC

    if args.command == "compile" and args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                canonical_json(compiled.artifact) + "\n", encoding="utf-8"
            )
        except OSError as exc:
            payload = {
                "status": "error",
                "command": "compile",
                "message": f"cannot write {args.out}: {exc}",
            }
            if args.json:
                _emit(payload, True)
            else:
                print(payload["message"], file=sys.stderr)
            return EXIT_USAGE
        payload = {
            "status": "ok",
            "command": "compile",
            "source": source_label,
            "artifact": str(args.out),
            "artifact_sha256": compiled.artifact["artifact_sha256"],
        }
        if args.json:
            _emit(payload, True)
        else:
            _emit(
                {
                    "message": f"OK: wrote {args.out} ({compiled.artifact['artifact_sha256']})"
                },
                False,
            )
        return EXIT_OK

    if args.command == "check":
        payload = {
            "status": "ok",
            "command": "check",
            "source": source_label,
            "diagnostics": [],
        }
        if args.json:
            _emit(payload, True)
        else:
            _emit({"message": f"OK: {source_label} is valid"}, False)
        return EXIT_OK

    payload = {
        "status": "ok",
        "command": "compile",
        "source": source_label,
        "artifact": compiled.artifact,
    }
    if args.json:
        _emit(payload, True)
    else:
        print(canonical_json(compiled.artifact))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
