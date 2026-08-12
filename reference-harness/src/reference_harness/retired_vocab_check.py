"""Deny-list gate: no retired vocabulary in active sources::

    uv run python -m reference_harness.retired_vocab_check <repo-root>

Two vocabularies have been retired repository-wide, and each is a class of
defect that sampling review cannot close: a retired spelling survives wherever
nobody happened to look, so the deny-list enumerates the class mechanically
instead.

**Temporal.** The root glossary's `_Avoid_` registry retires the
Reladomo-derived temporal spellings — business time/date, processing time/date,
effective date, system date, and the business/processing dimension family — in
favor of Valid Time / Transaction Time, and retires the camelCase dimension
spellings `validTime` / `transactionTime` in favor of the kebab-case enumerated
values `valid-time` / `transaction-time`.

**Query.** The recursive Operation wrapper tree was replaced by a Predicate (the
selection grammar) and an Object Query (the flat query value carrying it), so
every spelling that names a query, its grammar, or its wire form an *operation*
is retired: the module `m-op-algebra`, the package `op_algebra`, the schema
`operation.schema.json`, the read envelope's sibling `targetEntity` field, and
the Python `FindQuery` / `LoweredFindQuery` pair. Predicate, Object Query,
Includes, Deep Fetch, Subtype Selection, Temporal Selection, and Sort Key are
the accepted names.

Both deny-lists match whole retired PHRASES rather than bare words, because both
retired stems are ordinary English. A business/processing word counts only when
joined to a temporal noun, so "business key", "business/developer name", and
"operation processing" stay; "operation" counts only when joined to a
query-surface noun, so "write operation", "database operation boundary", and
`m-op-list` stay while "operation tree", "operation schema", and `op_algebra`
do not.

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
# credits the retired wrapper tree; the bare stem stays legal, which is what
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
)
_QUERY_SURFACE = "|".join(_QUERY_SURFACE_WORDS)

# Words retired only in the CAMEL compound: the spaced form is ordinary English
# ("the write operation rejected the row"), while the camel hump can only ever be
# a retired type name.
_QUERY_CAMEL_ONLY_WORDS = ("Rejected",)

# The retired stems themselves. `op` is included because the retired module,
# package, and schema all abbreviate it, and the same joined-word rule keeps
# `m-op-list` (a live module) legal.
_QUERY_STEMS = "op|operation|operations"

# Words that make the REVERSE order a retired query phrase — a query, or the act
# of judging one, named as an operation. This list is deliberately narrower than
# the surface-noun list above, because most words preceding "operation" qualify a
# genuine one: `blocking_operations`, "database operation boundary", "document
# operations", and the gate grammar's own `non-canonical-operation` all stay.
_QUERY_SUBJECT_WORDS = ("query", "find", "validate", "validation", "validator", "malformed")
_QUERY_SUBJECTS = "|".join(_QUERY_SUBJECT_WORDS)

_QUERY_CAMEL_STEMS = "|".join(
    f"[{stem[0]}{stem[0].upper()}]{stem[1:]}" for stem in ("op", "operation")
)
_QUERY_CAMEL_SURFACE = "|".join(
    [word.capitalize() for word in _QUERY_SURFACE_WORDS] + list(_QUERY_CAMEL_ONLY_WORDS)
)
_QUERY_CAMEL_SUBJECTS = "|".join(
    f"[{word[0]}{word[0].upper()}]{word[1:]}" for word in _QUERY_SUBJECT_WORDS
)

_RETIRED_TEMPORAL_PATTERNS = (
    re.compile(
        rf"{_LEFT}(?:business|processing)[\s/_-]+(?:{_TEMPORAL_NOUNS}){_RIGHT}", re.IGNORECASE
    ),
    re.compile(rf"{_LEFT}(?:business|processing)[_-](?:{_JOINED_WORDS}){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:[bB]usiness|[pP]rocessing)(?:{_CAMEL_WORDS}){_CAMEL_RIGHT}"),
    re.compile(rf"{_LEFT}(?:business|processing)[\s/_-]+as[\s_-]of{_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}effective[\s/_-]+dat(?:e|es|ed|ing){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}system[\s/_-]+date{_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:{'|'.join(_RETIRED_DIMENSION_SPELLINGS)}){_RIGHT}"),
)

_RETIRED_QUERY_PATTERNS = (
    re.compile(rf"{_LEFT}(?:{_QUERY_STEMS})[\s/_-]+(?:{_QUERY_SURFACE}){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:{_QUERY_SUBJECTS})[\s/_-]+(?:{_QUERY_STEMS}){_RIGHT}", re.IGNORECASE),
    re.compile(rf"{_LEFT}(?:{_QUERY_CAMEL_STEMS})(?:{_QUERY_CAMEL_SURFACE}){_CAMEL_RIGHT}"),
    re.compile(rf"{_LEFT}(?:{_QUERY_CAMEL_SUBJECTS})(?:Op|Operations?){_CAMEL_RIGHT}"),
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

# A URL, masked before matching: an issue slug or a vendor documentation anchor
# carries whatever vocabulary its issuing system fixed, and no edit here can
# change it.
_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+")

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


def check_text(relative_path: str, text: str) -> list[str]:
    """Every retired-vocabulary violation in *text* (empty ⇒ clean).

    Line-based: a ``_Avoid_`` line and every line of a paragraph opening
    ``Prior art:`` are exempt — both exist to NAME the retired spellings. A URL
    is masked before matching: its path is an external identifier fixed by
    whatever system issued it, not vocabulary this repository chooses.
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
        scanned = _URL.sub(lambda match: " " * len(match.group(0)), line)
        for family, patterns in _RETIRED_FAMILIES:
            for pattern in patterns:
                for match in pattern.finditer(scanned):
                    violations.append(
                        f"{relative_path}:{lineno}: retired {family} vocabulary {match.group(0)!r}"
                    )
    return violations


def main(argv: list[str]) -> int:
    """CLI entry point: scan every active-source file under the repo root
    *argv[0]*, reporting each violation on stderr as
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

    print("retired-vocabulary check OK: no retired temporal or query vocabulary in active sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
