"""Deny-list gate: no retired business/processing temporal vocabulary in
active sources::

    uv run python -m reference_harness.retired_vocab_check <repo-root>

The root glossary's `_Avoid_` registry retires the Reladomo-derived temporal
spellings — business time/date, processing time/date, effective date, system
date, and the business/processing dimension family — in favor of Valid Time /
Transaction Time. Prose, comments, docstrings, identifiers, and test names all
adopted the accepted vocabulary; this gate keeps a retired phrase from
reappearing on any active surface.

The deny-list matches whole retired PHRASES (a business/processing word joined
to a temporal noun, plus `effective date` / `system date`), never the bare
words "business" or "processing": non-temporal uses such as "business key",
"business/developer name", or "operation processing" are legitimate and stay.

Allow-list (explicitly labeled historical / prior-art / rejection text):

- ``docs/research/reladomo/**`` and every ``adr`` directory — Reladomo
  prior-art notes and historical decision records keep their original
  vocabulary (other research documents are active prose and are scanned);
- ``core/compatibility/descriptor-errors/`` — negative-test fixtures exist to
  spell the retired forms so serde provably rejects them;
- glossary ``_Avoid_`` lines and the labeled ``Prior art:`` paragraph — they
  name the retired spellings in order to retire them;
- this module's own test file, whose fixtures spell the retired phrases.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

__all__ = ["check_text", "main", "scanned_files"]

# Temporal nouns that make a business/processing compound a retired temporal
# phrase (any of whitespace, `/`, `_`, or `-` may join the words, so prose,
# snake_case identifiers, and kebab-case slugs are all covered).
_TEMPORAL_NOUN_WORDS = (
    "time",
    "times",
    "date",
    "dates",
    "dimension",
    "dimensions",
    "axis",
    "axes",
    "instant",
    "instants",
    "interval",
    "intervals",
    "milestone",
    "milestones",
    "coordinate",
    "coordinates",
    "coords",
    "history",
    "histories",
    "window",
    "windows",
    "bound",
    "bounds",
    "binds",
    "validity",
    "pin",
    "pins",
    "discriminator",
    "discriminators",
    "correction",
    "corrections",
)
_TEMPORAL_NOUNS = "|".join(_TEMPORAL_NOUN_WORDS)

# Words that are retired ONLY when joined by `-` / `_` (e.g. a
# business-from bound or a processing-latest read): the spaced forms are
# ordinary English ("separates the business from ...") and stay legal.
_JOINED_WORD_LIST = (
    "from",
    "until",
    "to",
    "at",
    "past",
    "latest",
    "only",
    "bounded",
    "temporal",
    "first",
)
_JOINED_WORDS = "|".join(_JOINED_WORD_LIST)

# camelCase identifier compounds (the retired instruction-field spellings and
# their kin), derived from the SAME word lists as the underscore/hyphen
# patterns so the camel coverage can never drift from them; matched
# case-sensitively so prose casing is left to the case-insensitive patterns
# above.
_CAMEL_WORDS = "|".join(word.capitalize() for word in _TEMPORAL_NOUN_WORDS + _JOINED_WORD_LIST)

# `\b` treats `_` as a word character, so identifier-embedded compounds
# (`keeps_the_business_bound`) would escape it; these lookarounds bound the
# phrase on non-alphanumerics instead.
_LEFT = r"(?<![A-Za-z0-9])"
_RIGHT = r"(?![A-Za-z0-9])"

# The camel compound's right boundary: a following lowercase letter or digit
# extends the token into a DIFFERENT identifier (`businessTimeout`,
# `businessTime2` — consistent with `_RIGHT`, which treats digits as word
# characters), while a following uppercase letter starts a new camel hump and
# IS a boundary (`businessFromValue` still carries the retired compound).
_CAMEL_RIGHT = r"(?![a-z0-9])"

_RETIRED_PATTERNS = (
    re.compile(
        rf"{_LEFT}(?:business|processing)[\s/_-]+(?:{_TEMPORAL_NOUNS}){_RIGHT}", re.IGNORECASE
    ),
    re.compile(rf"{_LEFT}(?:business|processing)[_-](?:{_JOINED_WORDS}){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:[bB]usiness|[pP]rocessing)(?:{_CAMEL_WORDS}){_CAMEL_RIGHT}"),
    re.compile(rf"{_LEFT}(?:business|processing)[\s/_-]+as[\s_-]of{_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}effective[\s/_-]+dat(?:e|es|ed|ing){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}system[\s/_-]+date{_RIGHT}", re.IGNORECASE),
)

# Only text-bearing source kinds participate; everything else (images, locks,
# build outputs) is not vocabulary surface.
_SCANNED_SUFFIXES = {
    ".md",
    ".py",
    ".yaml",
    ".yml",
    ".json",
    ".sql",
    ".toml",
    ".txt",
    ".cfg",
    ".ini",
}
_SCANNED_NAMES = {"justfile"}

# Directory names never descended into: tooling caches/outputs plus every
# `adr` directory (historical decision records keep their original prose).
_SKIPPED_DIR_NAMES = {"node_modules", "__pycache__", "dist", "adr"}

# Repo-root-relative subtrees exempt as historical / rejection-fixture text.
# Only the Reladomo prior-art notes are exempt under docs/research — every
# other research document is active prose and stays scanned.
_EXEMPT_TREES = ("docs/research/reladomo", "core/compatibility/descriptor-errors")

# Repo-root-relative files exempt because they exist to spell the retired
# phrases: this module (whose deny-list and examples name them) and its test
# fixtures.
_EXEMPT_FILES = {
    "reference-harness/src/reference_harness/retired_vocab_check.py",
    "reference-harness/tests/test_retired_vocab_check.py",
}


def _is_scanned_file(name: str) -> bool:
    if name.startswith("."):
        return False
    return name in _SCANNED_NAMES or Path(name).suffix in _SCANNED_SUFFIXES


def scanned_files(root: Path) -> Iterator[Path]:
    """Every active-source file under *root* the deny-list applies to."""
    for dirpath, dirnames, filenames in os.walk(root):
        relative_dir = Path(dirpath).relative_to(root).as_posix()
        kept: list[str] = []
        for name in sorted(dirnames):
            if name.startswith(".") or name in _SKIPPED_DIR_NAMES:
                continue
            child = name if relative_dir == "." else f"{relative_dir}/{name}"
            if child in _EXEMPT_TREES:
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            if not _is_scanned_file(name):
                continue
            relative = name if relative_dir == "." else f"{relative_dir}/{name}"
            if relative in _EXEMPT_FILES:
                continue
            yield Path(dirpath) / name


def check_text(relative_path: str, text: str) -> list[str]:
    """Every retired-vocabulary violation in *text* (empty ⇒ clean).

    Line-based: a ``_Avoid_`` line and every line of a paragraph opening
    ``Prior art:`` are exempt — both exist to NAME the retired spellings.
    """
    violations: list[str] = []
    block_start: str | None = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            block_start = None
            continue
        if block_start is None:
            block_start = stripped
        if stripped.startswith("_Avoid_") or block_start.startswith("Prior art:"):
            continue
        for pattern in _RETIRED_PATTERNS:
            for match in pattern.finditer(line):
                violations.append(
                    f"{relative_path}:{lineno}: retired temporal vocabulary {match.group(0)!r}"
                )
    return violations


def main(argv: list[str]) -> int:
    """CLI entry point: scan every active-source file under the repo root
    *argv[0]*, reporting each violation on stderr as
    ``path:line: retired temporal vocabulary '<match>'``.

    Exit codes: 0 — no retired temporal vocabulary on any scanned surface;
    1 — at least one violation; 2 — usage error (argument count, or *argv[0]*
    is not a directory).
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.retired_vocab_check <repo-root>",
            file=sys.stderr,
        )
        return 2
    root = Path(argv[0]).resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2

    violations: list[str] = []
    for path in scanned_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        violations.extend(check_text(path.relative_to(root).as_posix(), text))

    if violations:
        print(
            f"retired-vocabulary check FAILED ({len(violations)} violation(s)):",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("retired-vocabulary check OK: no retired temporal vocabulary in active sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
