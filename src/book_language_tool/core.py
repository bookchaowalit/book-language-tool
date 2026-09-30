"""Lexer, parser, compiler, and VM for the Book Language Tool.

The language is deliberately small and self-contained. It never delegates to
Python, a shell, or an operating-system process when running a program.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from typing import Any


MAX_INSTRUCTIONS = 10_000
# Resource bounds so hostile or accidental programs cannot exhaust memory/CPU
# or trip Python's int->str digit limit: signed 64-bit integers, 64 KiB strings
# and 100 levels of expression nesting (keeps the recursive-descent parser
# and compiler well inside Python's default recursion limit).
INT_MIN = -(2**63)
INT_MAX = 2**63 - 1
MAX_STRING_CHARS = 65_536
MAX_NESTING_DEPTH = 100
ARTIFACT_FORMAT = "book-language-tool.ir.v1"


@dataclass(frozen=True)
class Diagnostic:
    """A compiler/runtime finding.

    ``line``/``column``/``end_column`` are ``None`` when the finding has no
    source position (artifact format, digest or operand errors, and runtime
    errors in artifacts compiled without ``loc``); JSON output then carries
    ``null`` for all three instead of a fake ``1:1`` (text output omits the
    position).
    """

    code: str
    message: str
    line: int | None = None
    column: int | None = None
    end_column: int | None = None
    severity: str = "error"

    @property
    def has_location(self) -> bool:
        return self.line is not None and self.column is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "end_column": self.end_column,
        }


@dataclass(frozen=True)
class Token:
    kind: str
    lexeme: str
    literal: Any
    line: int
    column: int
    end_column: int


@dataclass(frozen=True)
class Literal:
    value: int | str
    line: int
    column: int


@dataclass(frozen=True)
class Variable:
    name: str
    line: int
    column: int


@dataclass(frozen=True)
class Unary:
    operator: str
    operand: Any
    line: int
    column: int


@dataclass(frozen=True)
class Binary:
    left: Any
    operator: str
    right: Any
    line: int
    column: int


@dataclass(frozen=True)
class LetStatement:
    name: str
    initializer: Any
    line: int
    column: int


@dataclass(frozen=True)
class PrintStatement:
    expression: Any
    line: int
    column: int


@dataclass(frozen=True)
class CompileResult:
    artifact: dict[str, Any] | None
    diagnostics: list[Diagnostic]


@dataclass(frozen=True)
class RunResult:
    artifact: dict[str, Any] | None
    output: list[str]
    diagnostics: list[Diagnostic]


class Lexer:
    """Turn source text into tokens and source-located diagnostics."""

    _identifier = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    _number = re.compile(r"[0-9]+")
    _keywords = {"let": "LET", "print": "PRINT"}
    _symbols = {
        "=": "EQUAL",
        "+": "PLUS",
        "-": "MINUS",
        "*": "STAR",
        "/": "SLASH",
        "(": "LEFT_PAREN",
        ")": "RIGHT_PAREN",
        ";": "SEMICOLON",
    }
    _escapes = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}

    def __init__(self, source: str) -> None:
        self.source = source
        self.start = 0
        self.current = 0
        self.line = 1
        self.column = 1
        self.token_line = 1
        self.token_column = 1
        self.tokens: list[Token] = []
        self.diagnostics: list[Diagnostic] = []

    def scan(self) -> tuple[list[Token], list[Diagnostic]]:
        while not self._at_end():
            self.start = self.current
            self.token_line = self.line
            self.token_column = self.column
            char = self._advance()
            if char in " \t\r\n":
                continue
            if char == "#":
                self._skip_comment()
                continue
            if char == '"':
                self._scan_string()
                continue
            if _is_ascii_digit(char):
                self._scan_number()
                continue
            if _is_ascii_letter(char) or char == "_":
                self._scan_identifier()
                continue
            kind = self._symbols.get(char)
            if kind:
                self._add_token(kind, char)
                continue
            self._error("L001", f"unexpected character {char!r}")

        self.tokens.append(Token("EOF", "", None, self.line, self.column, self.column))
        return self.tokens, self.diagnostics

    def _at_end(self) -> bool:
        return self.current >= len(self.source)

    def _advance(self) -> str:
        char = self.source[self.current]
        self.current += 1
        # "\n" and a lone "\r" (classic Mac line ending) end a line; the "\r"
        # of a "\r\n" pair is an ordinary column so the pair counts once.
        if char == "\n" or (char == "\r" and self._peek() != "\n"):
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char

    def _peek(self) -> str:
        return "\0" if self._at_end() else self.source[self.current]

    def _peek_next(self) -> str:
        return "\0" if self.current + 1 >= len(self.source) else self.source[self.current + 1]

    def _skip_comment(self) -> None:
        # Stop at a lone CR too, or a CR-only file is one long comment.
        while self._peek() not in ("\n", "\r", "\0"):
            self._advance()

    def _scan_string(self) -> None:
        value: list[str] = []
        while not self._at_end() and self._peek() != '"':
            if self._peek() in ("\n", "\r"):
                self._error("L002", "string literal cannot contain a raw newline")
                return
            if self._peek() == "\\":
                self._advance()
                if self._at_end():
                    break
                escaped = self._advance()
                if escaped not in self._escapes:
                    # Report and keep scanning to the closing quote so the
                    # rest of the literal does not cascade into L002.
                    self._error("L003", f"unknown string escape \\{escaped}")
                    continue
                value.append(self._escapes[escaped])
                continue
            value.append(self._advance())

        if self._at_end():
            self._error("L002", "unterminated string literal")
            return
        self._advance()
        if any(d.code == "L003" and d.line == self.token_line and d.column == self.token_column for d in self.diagnostics):
            return
        if len(value) > MAX_STRING_CHARS:
            self._error("L005", f"string literal exceeds {MAX_STRING_CHARS} characters")
            return
        self._add_token("STRING", "".join(value))

    def _scan_number(self) -> None:
        while _is_ascii_digit(self._peek()):
            self._advance()
        lexeme = self.source[self.start : self.current]
        if len(lexeme) > 19 or int(lexeme) > INT_MAX:
            self._error("L004", "integer literal is out of the 64-bit range")
            return
        self._add_token("NUMBER", int(lexeme))

    def _scan_identifier(self) -> None:
        while _is_ascii_letter(self._peek()) or _is_ascii_digit(self._peek()) or self._peek() == "_":
            self._advance()
        lexeme = self.source[self.start : self.current]
        self._add_token(self._keywords.get(lexeme, "IDENT"), lexeme)

    def _add_token(self, kind: str, literal: Any) -> None:
        lexeme = self.source[self.start : self.current]
        self.tokens.append(Token(kind, lexeme, literal, self.token_line, self.token_column, self.column))

    def _error(self, code: str, message: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                code=code,
                message=message,
                line=self.token_line,
                column=self.token_column,
                end_column=max(self.column, self.token_column + 1),
            )
        )


def _is_ascii_digit(char: str) -> bool:
    # str.isdigit() accepts "²" or "٣", which int() then rejects.
    return "0" <= char <= "9"


def _is_ascii_letter(char: str) -> bool:
    return ("a" <= char <= "z") or ("A" <= char <= "Z")


class ParseFailure(Exception):
    """Internal parser control flow carrying one user-facing diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class Parser:
    """Parse the intentionally small statement/expression grammar."""

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.current = 0
        self.depth = 0
        self.diagnostics: list[Diagnostic] = []

    def parse(self) -> tuple[list[Any], list[Diagnostic]]:
        statements: list[Any] = []
        while not self._check("EOF"):
            try:
                statements.append(self._statement())
            except ParseFailure as failure:
                self.depth = 0
                self.diagnostics.append(failure.diagnostic)
                self._synchronize()
        return statements, self.diagnostics

    def _statement(self) -> Any:
        if self._match("LET"):
            return self._let_statement(self._previous())
        if self._match("PRINT"):
            return self._print_statement(self._previous())
        token = self._peek()
        raise self._failure("P001", "expected 'let' or 'print' statement", token)

    def _let_statement(self, keyword: Token) -> LetStatement:
        name = self._consume("IDENT", "P002", "expected an identifier after 'let'")
        self._consume("EQUAL", "P003", "expected '=' after variable name")
        initializer = self._expression()
        self._consume("SEMICOLON", "P004", "expected ';' after variable declaration")
        return LetStatement(name.lexeme, initializer, keyword.line, keyword.column)

    def _print_statement(self, keyword: Token) -> PrintStatement:
        self._consume("LEFT_PAREN", "P005", "expected '(' after 'print'")
        expression = self._expression()
        self._consume("RIGHT_PAREN", "P006", "expected ')' after print expression")
        self._consume("SEMICOLON", "P004", "expected ';' after print statement")
        return PrintStatement(expression, keyword.line, keyword.column)

    def _expression(self) -> Any:
        return self._addition()

    def _enter(self) -> None:
        self.depth += 1
        if self.depth > MAX_NESTING_DEPTH:
            raise self._failure("P008", f"expression nesting exceeds {MAX_NESTING_DEPTH} levels", self._peek())

    def _addition(self) -> Any:
        expression = self._multiplication()
        while self._match("PLUS", "MINUS"):
            operator_token = self._previous()
            right = self._multiplication()
            expression = Binary(expression, operator_token.lexeme, right, operator_token.line, operator_token.column)
        return expression

    def _multiplication(self) -> Any:
        expression = self._unary()
        while self._match("STAR", "SLASH"):
            operator_token = self._previous()
            right = self._unary()
            expression = Binary(expression, operator_token.lexeme, right, operator_token.line, operator_token.column)
        return expression

    def _unary(self) -> Any:
        if self._match("MINUS"):
            operator = self._previous()
            self._enter()
            operand = self._unary()
            self.depth -= 1
            return Unary(operator.lexeme, operand, operator.line, operator.column)
        return self._primary()

    def _primary(self) -> Any:
        if self._match("NUMBER", "STRING"):
            token = self._previous()
            return Literal(token.literal, token.line, token.column)
        if self._match("IDENT"):
            token = self._previous()
            return Variable(token.lexeme, token.line, token.column)
        if self._match("LEFT_PAREN"):
            self._enter()
            expression = self._expression()
            self.depth -= 1
            self._consume("RIGHT_PAREN", "P006", "expected ')' after expression")
            return expression
        raise self._failure("P007", "expected an integer, string, identifier, or '('", self._peek())

    def _consume(self, kind: str, code: str, message: str) -> Token:
        if self._check(kind):
            return self._advance()
        raise self._failure(code, message, self._peek())

    def _match(self, *kinds: str) -> bool:
        for kind in kinds:
            if self._check(kind):
                self._advance()
                return True
        return False

    def _check(self, *kinds: str) -> bool:
        return self._peek().kind in kinds

    def _advance(self) -> Token:
        if not self._check("EOF"):
            self.current += 1
        return self._previous()

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    def _failure(self, code: str, message: str, token: Token) -> ParseFailure:
        return ParseFailure(
            Diagnostic(code, message, token.line, token.column, token.end_column)
        )

    def _synchronize(self) -> None:
        while not self._check("EOF"):
            if self._previous().kind == "SEMICOLON":
                return
            if self._check("LET", "PRINT"):
                return
            self._advance()


class Compiler:
    """Compile AST nodes to a small JSON-compatible instruction set."""

    def __init__(self) -> None:
        self.instructions: list[dict[str, Any]] = []
        self.defined: set[str] = set()
        self.diagnostics: list[Diagnostic] = []

    def compile(self, statements: list[Any]) -> tuple[list[dict[str, Any]], list[Diagnostic]]:
        for statement in statements:
            if isinstance(statement, LetStatement):
                if statement.name in self.defined:
                    self.diagnostics.append(
                        Diagnostic(
                            "S002",
                            f"variable {statement.name!r} is already declared",
                            statement.line,
                            statement.column,
                            statement.column + len(statement.name),
                        )
                    )
                    continue
                self._expression(statement.initializer)
                self._emit("STORE", statement.name, statement)
                self.defined.add(statement.name)
            elif isinstance(statement, PrintStatement):
                self._expression(statement.expression)
                self._emit("PRINT", node=statement)
        if not self.diagnostics:
            self._emit("HALT")
        return self.instructions, self.diagnostics

    def _expression(self, expression: Any) -> None:
        if isinstance(expression, Literal):
            self._emit("CONST", expression.value, expression)
            return
        if isinstance(expression, Variable):
            if expression.name not in self.defined:
                self.diagnostics.append(
                    Diagnostic(
                        "S001",
                        f"variable {expression.name!r} is not declared",
                        expression.line,
                        expression.column,
                        expression.column + len(expression.name),
                    )
                )
                return
            self._emit("LOAD", expression.name, expression)
            return
        if isinstance(expression, Unary):
            self._expression(expression.operand)
            self._emit("NEG", node=expression)
            return
        if isinstance(expression, Binary):
            self._expression(expression.left)
            self._expression(expression.right)
            self._emit(
                {
                    "+": "ADD",
                    "-": "SUB",
                    "*": "MUL",
                    "/": "DIV",
                }[expression.operator],
                node=expression,
            )

    def _emit(self, operation: str, argument: Any = None, node: Any = None) -> None:
        instruction: dict[str, Any] = {"op": operation}
        if argument is not None:
            instruction["arg"] = argument
        if node is not None:
            # Optional source location so runtime diagnostics point at the
            # expression or statement that produced the instruction.
            instruction["loc"] = [node.line, node.column]
        self.instructions.append(instruction)


class VM:
    """Execute only the Book Language Tool instruction set."""

    def run(self, artifact: dict[str, Any]) -> tuple[list[str], list[Diagnostic]]:
        diagnostics = self._validate_artifact(artifact)
        if diagnostics:
            return [], diagnostics
        output, diagnostics, failed_at = self._execute(artifact["instructions"])
        if diagnostics and failed_at is not None:
            loc = artifact["instructions"][failed_at].get("loc")
            if loc is not None:
                line, column = loc
                diagnostics = [replace(d, line=line, column=column, end_column=column + 1) for d in diagnostics]
        return output, diagnostics

    def _execute(self, instructions: list[dict[str, Any]]) -> tuple[list[str], list[Diagnostic], int | None]:
        """Run validated instructions; on failure also return the failing index."""

        stack: list[Any] = []
        variables: dict[str, Any] = {}
        output: list[str] = []
        for index, instruction in enumerate(instructions):
            if index >= MAX_INSTRUCTIONS:
                return [], [Diagnostic("R005", "instruction limit exceeded")], index
            operation = instruction["op"]
            argument = instruction.get("arg")
            if operation == "CONST":
                stack.append(argument)
            elif operation == "STORE":
                if not stack:
                    return [], [Diagnostic("R004", "malformed STORE instruction")], index
                variables[str(argument)] = stack.pop()
            elif operation == "LOAD":
                name = str(argument)
                if name not in variables:
                    return [], [Diagnostic("R001", f"variable {name!r} is not available")], index
                stack.append(variables[name])
            elif operation == "NEG":
                value, error = self._pop(stack, "NEG")
                if error:
                    return [], [error], index
                if not isinstance(value, int):
                    return [], [Diagnostic("R003", "unary '-' requires an integer")], index
                if -value > INT_MAX:
                    return [], [Diagnostic("R006", "integer overflow (64-bit range)")], index
                stack.append(-value)
            elif operation in {"ADD", "SUB", "MUL", "DIV"}:
                right, error = self._pop(stack, operation)
                if error:
                    return [], [error], index
                left, error = self._pop(stack, operation)
                if error:
                    return [], [error], index
                result, diagnostic = self._binary(left, operation, right)
                if diagnostic:
                    return [], [diagnostic], index
                stack.append(result)
            elif operation == "PRINT":
                value, error = self._pop(stack, "PRINT")
                if error:
                    return [], [error], index
                output.append(str(value))
            elif operation == "HALT":
                return output, [], None
            else:
                return [], [Diagnostic("R004", f"unknown instruction {operation!r}")], index
        return output, [], None

    def _validate_artifact(self, artifact: dict[str, Any]) -> list[Diagnostic]:
        if not isinstance(artifact, dict) or artifact.get("format") != ARTIFACT_FORMAT:
            return [Diagnostic("R004", "artifact format is not supported")]
        instructions = artifact.get("instructions")
        if not isinstance(instructions, list) or not instructions:
            return [Diagnostic("R004", "artifact instructions are missing")]
        payload = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
        expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        if artifact.get("artifact_sha256") != expected:
            return [Diagnostic("R004", "artifact digest does not match its contents")]
        for instruction in instructions:
            if not isinstance(instruction, dict) or not isinstance(instruction.get("op"), str):
                return [Diagnostic("R004", "artifact contains an invalid instruction")]
            # The digest proves integrity, not origin: anyone can re-hash an
            # edited artifact, so operands are validated like untrusted input.
            operation = instruction["op"]
            argument = instruction.get("arg")
            if operation == "CONST" and not _valid_value(argument):
                return [Diagnostic("R004", "CONST operand must be a bounded integer or string")]
            if operation in {"LOAD", "STORE"} and not (
                isinstance(argument, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", argument)
            ):
                return [Diagnostic("R004", f"{operation} operand must be an identifier")]
            if "loc" in instruction and not _valid_loc(instruction["loc"]):
                return [Diagnostic("R004", "instruction loc must be [line, column] positive integers")]
        return []

    @staticmethod
    def _pop(stack: list[Any], operation: str) -> tuple[Any, Diagnostic | None]:
        if not stack:
            return None, Diagnostic("R004", f"malformed {operation} instruction")
        return stack.pop(), None

    @staticmethod
    def _binary(left: Any, operation: str, right: Any) -> tuple[Any, Diagnostic | None]:
        result, diagnostic = VM._binary_unchecked(left, operation, right)
        if diagnostic is None and not _valid_value(result):
            if isinstance(result, str):
                return None, Diagnostic("R007", f"string exceeds {MAX_STRING_CHARS} characters")
            return None, Diagnostic("R006", "integer overflow (64-bit range)")
        return result, diagnostic

    @staticmethod
    def _binary_unchecked(left: Any, operation: str, right: Any) -> tuple[Any, Diagnostic | None]:
        if operation == "ADD" and isinstance(left, str) and isinstance(right, str):
            if len(left) + len(right) > MAX_STRING_CHARS:
                return None, Diagnostic("R007", f"string exceeds {MAX_STRING_CHARS} characters")
            return left + right, None
        if not isinstance(left, int) or not isinstance(right, int):
            return None, Diagnostic("R003", f"operator {operation} requires integer operands")
        if operation == "MUL" and left and right and abs(left) > INT_MAX // abs(right) + 1:
            # Reject before multiplying so huge products are never materialised.
            return None, Diagnostic("R006", "integer overflow (64-bit range)")
        if operation == "ADD":
            return left + right, None
        if operation == "SUB":
            return left - right, None
        if operation == "MUL":
            return left * right, None
        if operation == "DIV":
            if right == 0:
                return None, Diagnostic("R002", "division by zero")
            return left // right, None
        return None, Diagnostic("R004", f"unsupported binary operation {operation!r}")


def _valid_loc(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(part, int) and not isinstance(part, bool) and 1 <= part <= 10**9 for part in value)
    )


def _valid_value(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return INT_MIN <= value <= INT_MAX
    if isinstance(value, str):
        return len(value) <= MAX_STRING_CHARS
    return False


def canonical_json(value: Any) -> str:
    """Serialize artifacts deterministically for stable diffs and hashes."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compile_source(source: str) -> CompileResult:
    tokens, lexical_diagnostics = Lexer(source).scan()
    if lexical_diagnostics:
        return CompileResult(None, lexical_diagnostics)
    statements, parse_diagnostics = Parser(tokens).parse()
    if parse_diagnostics:
        return CompileResult(None, parse_diagnostics)
    instructions, semantic_diagnostics = Compiler().compile(statements)
    if semantic_diagnostics:
        return CompileResult(None, semantic_diagnostics)

    payload = {
        "format": ARTIFACT_FORMAT,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "instructions": instructions,
    }
    artifact = dict(payload)
    artifact["artifact_sha256"] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return CompileResult(artifact, [])


def run_source(source: str) -> RunResult:
    compiled = compile_source(source)
    if compiled.diagnostics or compiled.artifact is None:
        return RunResult(None, [], compiled.diagnostics)
    output, diagnostics = VM().run(compiled.artifact)
    return RunResult(compiled.artifact, output, diagnostics)


def diagnostic_rows(diagnostics: list[Diagnostic]) -> list[dict[str, Any]]:
    return [diagnostic.as_dict() for diagnostic in diagnostics]
