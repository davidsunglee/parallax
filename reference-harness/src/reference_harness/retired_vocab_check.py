"""Deny-list gate: no retired vocabulary in active sources::

    uv run python -m reference_harness.retired_vocab_check <repo-root>

Two vocabularies are retired repository-wide. A retired spelling survives
wherever nobody happens to look, so the deny-list enumerates both mechanically
over every active source file — its text and its repository-relative path, since
a module, a schema, and a corpus case each carry vocabulary in their filename.

**Temporal.** The root glossary's `_Avoid_` registry retires the
Reladomo-derived temporal spellings — business time/date, processing time/date,
effective date, system date, and the business/processing dimension family — in
favor of Valid Time / Transaction Time, and retires the camelCase dimension
spellings `validTime` / `transactionTime` in favor of the kebab-case enumerated
values `valid-time` / `transaction-time`.

**Query.** A read is an Object Query carrying a Predicate; neither is an
*operation*. Every spelling that names a query, its grammar, its wire form, or
the machinery that reads one an *operation* is retired: the module
`m-op-algebra`, the package `op_algebra`, the schema `operation.schema.json`,
the read envelope's sibling `targetEntity` field, and the `FindQuery` /
`LoweredFindQuery` pair. Predicate, Object Query, Includes, Deep Fetch, Subtype
Selection, Temporal Selection, and Sort Key are the accepted names.

Both deny-lists match whole retired PHRASES rather than bare words, because both
retired stems are ordinary English. A business/processing word counts only when
joined to a temporal noun, so "business key", "business/developer name", and
"operation processing" stay; "operation" counts only when joined to a
query-surface noun, so "write operation", "database operation boundary", and
`m-op-list` stay while "operation tree", "operation schema", and `op_algebra`
do not. A phrase counts wherever it is written — in prose, in a camelCase or
SCREAMING_SNAKE identifier, in a path component, and across the line break a
wrapped document puts in the middle of it.

Allow-list (explicitly labeled historical / prior-art / rejection text):

- ``docs/research/reladomo/**`` — prior-art notes keep the vocabulary of the
  system they describe (other research documents are active prose and are
  scanned);
- every ``adr`` directory, for the TEMPORAL family only — a decision record
  states the temporal vocabulary current when it was written. The query
  deny-list still applies there, because a decision record names live
  machinery;
- ``core/compatibility/descriptor-errors/`` — negative-test fixtures exist to
  spell the retired forms so serde provably rejects them;
- glossary ``_Avoid_`` lines, the labeled ``Prior art:`` paragraph, and a table
  whose first header cell is ``Retired`` — they name the retired spellings in
  order to retire them;
- this module's own test file, whose fixtures spell the retired phrases.
"""

from __future__ import annotations

import bisect
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

__all__ = ["check_path", "check_text", "main", "scanned_files"]

# The joiner between a compound phrase's words: whitespace, `/`, `_`, or `-`,
# spanning at most one line break. One break is the wrap a hard-wrapped document
# puts inside a phrase; two are a paragraph boundary, where the words on either
# side belong to different sentences. Only indentation may follow the break —
# a `-` opening the next line is a list bullet, not a joiner.
_JOIN = r"(?:[ \t/_-]+\n?[ \t]*|\n[ \t]*)"

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

# The retired camelCase spellings of the temporal dimension vocabulary, whose
# accepted forms are the kebab-case enumerated values `valid-time` and
# `transaction-time`. Matched case-sensitively on the lowercase-initial form:
# the core algebra's `ValidTime` / `TransactionTime` variant names are a
# different surface and stay legal.
_RETIRED_DIMENSION_SPELLINGS = ("validTime", "transactionTime")

# The camel compound's right boundary: a following lowercase letter or digit
# extends the token into a DIFFERENT identifier (`businessTimeout`,
# `businessTime2` — consistent with `_RIGHT`, which treats digits as word
# characters), while a following uppercase letter starts a new camel hump and
# IS a boundary (`businessFromValue` still carries the retired compound).
_CAMEL_RIGHT = r"(?![a-z0-9])"

# Nouns that make an `operation` / `op` compound a retired QUERY phrase. Each
# names the query, its grammar, or the machinery that reads one, so the compound
# credits the retired representation; the bare stem stays legal, which is what
# keeps "write operation", "database operation boundary", and `m-op-list` out of
# the deny-list.
_QUERY_SURFACE_WORDS = (
    "algebra",
    "algebras",
    "tree",
    "trees",
    "wrapper",
    "wrappers",
    "node",
    "nodes",
    "spine",
    "spines",
    "union",
    "unions",
    "grammar",
    "grammars",
    "envelope",
    "envelopes",
    "document",
    "documents",
    "schema",
    "schemas",
    "serde",
    "clause",
    "clauses",
    "directive",
    "directives",
    "field",
    "fields",
    "builder",
    "builders",
    "lowering",
    "validate",
    "validation",
    "validator",
    "reference",
    "references",
    "query",
    "queries",
    "predicate",
    "predicates",
    "backed",
    "error",
    "errors",
    "url",
    "urls",
    "dispatch",
    "narrow",
    "narrows",
    "narrowing",
    "mix",
    "mixes",
    "drift",
    "plan",
    "plans",
    "cache",
    "caches",
    "caching",
    "spelling",
    "spellings",
)
_QUERY_SURFACE = "|".join(_QUERY_SURFACE_WORDS)

# One connective the retired compound may carry between the stem and its surface
# noun, so `operation no-drift` and `operation-to-result` read as the single
# phrases they are.
_QUERY_CONNECTIVE_WORDS = ("to", "no")
_QUERY_CONNECTIVE = rf"(?:(?:{'|'.join(_QUERY_CONNECTIVE_WORDS)}){_JOIN})?"

# Words retired only when `-` or `_` joins them to the stem, in either order.
# The spaced form is ordinary English — "the write operation rejected the row",
# a write tree's root operation, "transactions and operation results" — while
# the joined form is an identifier, where the only thing being named is a query.
_QUERY_JOINED_WORD_LIST = ("rejected", "root", "inner", "embedded", "result", "results")
_QUERY_JOINED_WORDS = "|".join(_QUERY_JOINED_WORD_LIST)

# The retired stems themselves, longest first. `op` is included because the
# retired module, package, and schema all abbreviate it, and the surface-noun
# rule keeps `m-op-list` (a live module) legal.
_QUERY_STEM_WORDS = ("operations", "operation", "op")
_QUERY_STEMS = "|".join(_QUERY_STEM_WORDS)

# The joined-word patterns use these instead, because a bare `op` joined to a
# position word is the navigation filter's inner operand (`inner_op`,
# `Exists.op`) — a live wire spelling — not a query named as an operation.
_QUERY_FULL_STEM_WORDS = ("operations", "operation")
_QUERY_FULL_STEMS = "|".join(_QUERY_FULL_STEM_WORDS)

# Words that make the REVERSE order a retired query phrase — a query, or the act
# of judging one, named as an operation. This list is deliberately narrower than
# the surface-noun list above, because most words preceding "operation" qualify a
# genuine one: `blocking_operations`, "database operation boundary", "document
# operations", and the gate grammar's own `non-canonical-operation` all stay.
_QUERY_SUBJECT_WORDS = (
    "query",
    "find",
    "validate",
    "validation",
    "validator",
    "malformed",
    "equal",
)
_QUERY_SUBJECTS = "|".join(_QUERY_SUBJECT_WORDS)


def _camel_either_case(word: str) -> str:
    return f"[{word[0]}{word[0].upper()}]{word[1:]}"


# camelCase compounds, derived from the SAME word lists as the spaced and joined
# patterns so the camel coverage can never drift from them. The stems keep their
# plural, so `OperationsTree` is caught alongside `OperationTree`.
_QUERY_CAMEL_STEMS = "|".join(_camel_either_case(stem) for stem in _QUERY_STEM_WORDS)
_QUERY_CAMEL_FULL_STEMS = "|".join(_camel_either_case(stem) for stem in _QUERY_FULL_STEM_WORDS)
_QUERY_CAMEL_CONNECTIVE = rf"(?:{'|'.join(word.capitalize() for word in _QUERY_CONNECTIVE_WORDS)})?"
_QUERY_CAMEL_SURFACE = "|".join(word.capitalize() for word in _QUERY_SURFACE_WORDS)
_QUERY_CAMEL_JOINED = "|".join(word.capitalize() for word in _QUERY_JOINED_WORD_LIST)
_QUERY_CAMEL_SUBJECTS = "|".join(_camel_either_case(word) for word in _QUERY_SUBJECT_WORDS)

_RETIRED_TEMPORAL_PATTERNS = (
    re.compile(
        rf"{_LEFT}(?:business|processing){_JOIN}(?:{_TEMPORAL_NOUNS}){_RIGHT}", re.IGNORECASE
    ),
    re.compile(rf"{_LEFT}(?:business|processing)[_-](?:{_JOINED_WORDS}){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:[bB]usiness|[pP]rocessing)(?:{_CAMEL_WORDS}){_CAMEL_RIGHT}"),
    re.compile(rf"{_LEFT}(?:business|processing){_JOIN}as[\s_-]of{_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}effective{_JOIN}dat(?:e|es|ed|ing){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}system{_JOIN}date{_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:{'|'.join(_RETIRED_DIMENSION_SPELLINGS)}){_RIGHT}"),
)

_RETIRED_QUERY_PATTERNS = (
    re.compile(
        rf"{_LEFT}(?:{_QUERY_STEMS}){_JOIN}{_QUERY_CONNECTIVE}(?:{_QUERY_SURFACE}){_RIGHT}",
        re.IGNORECASE,
    ),
    re.compile(rf"{_LEFT}(?:{_QUERY_SUBJECTS}){_JOIN}(?:{_QUERY_STEMS}){_RIGHT}", re.IGNORECASE),
    re.compile(
        rf"{_LEFT}(?:{_QUERY_FULL_STEMS})[_-](?:(?:{'|'.join(_QUERY_CONNECTIVE_WORDS)})[_-])?"
        rf"(?:{_QUERY_JOINED_WORDS}){_RIGHT}",
        re.IGNORECASE,
    ),
    re.compile(
        rf"{_LEFT}(?:{_QUERY_JOINED_WORDS})[_-](?:{_QUERY_FULL_STEMS}){_RIGHT}", re.IGNORECASE
    ),
    re.compile(
        rf"{_LEFT}(?:{_QUERY_CAMEL_STEMS}){_QUERY_CAMEL_CONNECTIVE}"
        rf"(?:{_QUERY_CAMEL_SURFACE}){_CAMEL_RIGHT}"
    ),
    re.compile(
        rf"{_LEFT}(?:{_QUERY_CAMEL_FULL_STEMS}){_QUERY_CAMEL_CONNECTIVE}"
        rf"(?:{_QUERY_CAMEL_JOINED}){_CAMEL_RIGHT}"
    ),
    re.compile(rf"{_LEFT}(?:{_QUERY_CAMEL_SUBJECTS})(?:Op|Operations?){_CAMEL_RIGHT}"),
    re.compile(rf"{_LEFT}(?:{_QUERY_CAMEL_JOINED})(?:Operations?){_CAMEL_RIGHT}"),
    # The retired schema filename, whose `.` joiner is deliberately not in the
    # general compound pattern: an ordinary sentence break before a capitalized
    # "Schema" would otherwise match.
    re.compile(rf"{_LEFT}operation\.schema\.json", re.IGNORECASE),
    # The retired read envelope's sibling entity field. Only the identifier
    # spellings are retired — the prose phrase "target entity" describes a
    # relationship's far side and stays.
    re.compile(rf"{_LEFT}[tT]arget(?:Entity|_entity){_RIGHT}"),
    # The retired fluent query type, in its identifier spellings only: the
    # spaced form is ordinary English ("the trailing find queries the open
    # set"), so only the joined and camel spellings are denied. The camel
    # pattern carries no left boundary, which is what catches
    # `LoweredFindQuery` as well as the bare name.
    re.compile(rf"{_LEFT}find[_-]quer(?:y|ies){_RIGHT}", re.IGNORECASE),
    re.compile(rf"FindQuer(?:y|ies){_CAMEL_RIGHT}"),
)

_RETIRED_FAMILIES = (
    ("temporal", _RETIRED_TEMPORAL_PATTERNS),
    ("query", _RETIRED_QUERY_PATTERNS),
)

# A URL, masked before matching: its text is fixed by whatever system issued it,
# so no edit in this repository can change the vocabulary it spells.
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+")

# The masking character. It is not alphanumeric, so it bounds a phrase the same
# way punctuation does, and it is not a joiner, so masked text can never become
# the middle of a compound that spans it.
_MASK = "\x00"

# A line opening a block that exists to NAME retired spellings; every line of the
# block is exempt. A `_Avoid_` line is exempt on its own.
_EXEMPT_BLOCK_OPENERS = ("Prior art:", "| Retired |")
_EXEMPT_LINE_OPENER = "_Avoid_"

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

# Directory names never descended into: tooling caches and build outputs, which
# are not vocabulary surface.
_SKIPPED_DIR_NAMES = {"node_modules", "__pycache__", "dist"}

# Repo-root-relative subtrees exempt as historical / rejection-fixture text.
# Only the Reladomo prior-art notes are exempt under docs/research — every
# other research document is active prose and stays scanned.
_EXEMPT_TREES = ("docs/research/reladomo", "core/compatibility/descriptor-errors")

# A directory whose documents state the temporal vocabulary current when they
# were written. Only that family is exempt: a decision record also names live
# machinery, and the name of a live guard, module, or type is current prose.
_TEMPORAL_EXEMPT_DIR_NAME = "adr"

# Repo-root-relative files exempt because they exist to spell the retired
# phrases: this module (whose deny-list and examples name them) and its test
# fixtures.
_EXEMPT_FILES = {
    "reference-harness/src/reference_harness/retired_vocab_check.py",
    "reference-harness/tests/contract_tools/test_retired_vocab_check.py",
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


def _applicable_families(relative_path: str) -> tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]:
    directories = relative_path.split("/")[:-1]
    if _TEMPORAL_EXEMPT_DIR_NAME in directories:
        return tuple(entry for entry in _RETIRED_FAMILIES if entry[0] != "temporal")
    return _RETIRED_FAMILIES


def _masked(text: str) -> str:
    """*text* with every exempt line and every URL replaced by ``_MASK``.

    Masking rather than dropping keeps every offset, so a match's position still
    identifies the line it was written on.
    """
    masked: list[str] = []
    block_start: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            block_start = None
        elif block_start is None:
            block_start = stripped
        exempt = stripped and (
            stripped.startswith(_EXEMPT_LINE_OPENER)
            or (block_start is not None and block_start.startswith(_EXEMPT_BLOCK_OPENERS))
        )
        if exempt:
            masked.append(_MASK * len(line))
        else:
            masked.append(_URL.sub(lambda match: _MASK * len(match.group(0)), line))
    return "\n".join(masked)


def check_text(relative_path: str, text: str) -> list[str]:
    """Every retired-vocabulary violation in *text* (empty ⇒ clean).

    A ``_Avoid_`` line, every line of a paragraph opening ``Prior art:``, every
    row of a table whose first header cell is ``Retired``, and every URL are
    masked before matching: each exists to spell a name this repository does not
    choose. Matching runs over the whole document rather than line by line, so a
    phrase wrapped across a line break is caught at the line it starts on.
    """
    scanned = _masked(text)
    line_starts = [0]
    for index, character in enumerate(scanned):
        if character == "\n":
            line_starts.append(index + 1)
    violations: list[str] = []
    for family, patterns in _applicable_families(relative_path):
        for pattern in patterns:
            for match in pattern.finditer(scanned):
                lineno = bisect.bisect_right(line_starts, match.start())
                phrase = " ".join(match.group(0).split())
                violations.append(
                    f"{relative_path}:{lineno}: retired {family} vocabulary {phrase!r}"
                )
    return violations


def check_path(relative_path: str) -> list[str]:
    """Every retired-vocabulary violation in *relative_path* itself.

    A module, a schema, and a corpus case name their subject in the filename, so
    the path is vocabulary surface in its own right and a retired spelling can
    survive there while every line of the file is clean.
    """
    violations: list[str] = []
    for family, patterns in _applicable_families(relative_path):
        for pattern in patterns:
            for match in pattern.finditer(relative_path):
                violations.append(
                    f"{relative_path}: retired {family} vocabulary {match.group(0)!r} in the path"
                )
    return violations


def main(argv: list[str]) -> int:
    """CLI entry point: scan every active-source file under the repo root
    *argv[0]* — its path and then its text — reporting each violation on stderr
    as ``path: retired <family> vocabulary '<match>' in the path`` or
    ``path:line: retired <family> vocabulary '<match>'``.

    Exit codes: 0 — no retired temporal or query vocabulary on any scanned
    surface; 1 — at least one violation; 2 — usage error (argument count, or
    *argv[0]* is not a directory).
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
        relative = path.relative_to(root).as_posix()
        violations.extend(check_path(relative))
        violations.extend(check_text(relative, path.read_text(encoding="utf-8", errors="replace")))

    if violations:
        print(
            f"retired-vocabulary check FAILED ({len(violations)} violation(s)):",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("retired-vocabulary check OK: no retired temporal or query vocabulary in active sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
