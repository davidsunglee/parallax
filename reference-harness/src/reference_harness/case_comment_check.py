"""Comment-placement gate for compatibility cases: one leading header comment
block, then a comment-free body::

    uv run python -m reference_harness.case_comment_check <compatibility-dir>

`m-case-format.md`'s house style requires every case to open with a header
comment — the ONLY comments a case carries. The grouped `given` / `when` /
`then` structure shows what mid-document comments used to narrate, so after
the leading header block a case may contain no full-line and no inline
comment. This gate mechanizes that rule.

Line-based and conservative: a full-line comment is a line whose first
non-blank character is ``#``; an inline comment is an unquoted ``#`` preceded
by whitespace on a content line. Lines inside a literal/folded block scalar
(golden SQL and other multi-line values) are never inspected, and a ``#``
inside a quoted scalar is data, not a comment.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

__all__ = ["case_comment_violations", "main"]

# A literal (`|`) or folded (`>`) block-scalar introducer at end of line,
# with optional YAML indentation / chomping indicators (`|2`, `|-`, `>+`, …).
_BLOCK_SCALAR_INTRODUCER = re.compile(r"(?:^|[\s:])[|>][0-9]*[+-]?[0-9]*$")


def _has_inline_comment(line: str) -> bool:
    """Whether *line* carries a YAML comment after content: an unquoted ``#``
    preceded by whitespace (YAML's own inline-comment rule, approximated with
    per-line single/double-quote tracking). Inside a double-quoted scalar a
    backslash escapes the next character, so an escaped ``\\"`` does not close
    the scalar; a single-quoted scalar has no backslash escapes — YAML doubles
    the quote (``''``) instead, which close-then-reopen tracking already treats
    as staying inside quoted text."""
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if quote is not None:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "#" and index > 0 and line[index - 1] in {" ", "\t"}:
            return True
        index += 1
    return False


def case_comment_violations(text: str) -> list[tuple[int, str]]:
    """Every ``(line number, message)`` comment-placement violation in a case
    document (empty ⇒ conforming). A case must OPEN with its header comment
    block; every comment after that block — full-line or inline, even after a
    blank line — is a violation."""
    lines = text.splitlines()
    header_end = 0
    while header_end < len(lines) and lines[header_end].lstrip().startswith("#"):
        header_end += 1
    if header_end == 0:
        return [(1, "missing the required leading header comment")]

    violations: list[tuple[int, str]] = []
    block_indent: int | None = None
    for offset in range(header_end, len(lines)):
        line = lines[offset]
        lineno = offset + 1
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if block_indent is not None:
            if not stripped or indent > block_indent:
                continue
            block_indent = None
        if not stripped:
            continue
        if stripped.startswith("#"):
            violations.append((lineno, "full-line comment after the case header"))
            continue
        if _has_inline_comment(line):
            violations.append((lineno, "inline comment after the case header"))
        if _BLOCK_SCALAR_INTRODUCER.search(stripped):
            block_indent = indent
    return violations


def main(argv: list[str]) -> int:
    """CLI entry point: check every ``*.yaml`` case under *argv[0]*'s
    ``cases/`` directory, reporting each violation on stderr as
    ``path:line: message``.

    Exit codes: 0 — every case is header-comment-only; 1 — at least one
    comment-placement violation; 2 — usage error (argument count, or *argv[0]*
    has no ``cases/`` directory).
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.case_comment_check <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    cases_dir = Path(argv[0]) / "cases"
    if not cases_dir.is_dir():
        print(f"not a directory: {cases_dir}", file=sys.stderr)
        return 2

    failures: list[str] = []
    for path in sorted(cases_dir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        failures.extend(
            f"{path}:{lineno}: {message}" for lineno, message in case_comment_violations(text)
        )

    if failures:
        print(
            f"case comment-placement check FAILED ({len(failures)} violation(s)):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("case comment-placement check OK: every case is header-comment-only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
