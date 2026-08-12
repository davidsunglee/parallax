"""Deny-list gate: no retired vocabulary in active sources::

    uv run python -m reference_harness.retired_vocab_check <repo-root>

Two vocabularies are retired repository-wide. A retired spelling survives
wherever nobody happens to look, so the deny-list enumerates both mechanically
over every active source file — its text and its repository-relative path, since
a module, a schema, and a corpus case each carry vocabulary in their filename.
Active is git's own view of the working tree: every tracked file plus every
untracked one it does not ignore, whatever its directory or suffix.

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
retired stems are ordinary English. What makes a phrase retired depends on where
it is written:

- in prose, the stem counts only beside a listed noun — a temporal noun for
  business/processing, a query-surface noun for operation — so "business key",
  "business/developer name", "operation processing", "write operation", and
  "database operation boundary" stay while "operation tree" and "operation
  schema" do not;
- an identifier or path component the stem OPENS names its subject an
  operation whatever word follows, so `op_algebra`, `op_root`, `operation_model`,
  and `core/op/nodes.py` count without their second word being listed;
- a camelCase hump bounds a word the way punctuation does, so a capitalized stem
  counts wherever it sits inside an identifier: `myOperationTree`,
  `buildOperationsSchema`, and `parseOperationDocument` are the compound their
  hump spells, as are `entityBusinessDate` and `opTree`.

Three things the compound rules deliberately do not decide, each because this
repository spells the same shape for a live subject:

- the bare stem in prose, which stays legal in every sense that is not a query
  ("a write operation", "the business key");
- the full stem hyphenated, or sitting deeper inside a snake_case name, where the
  compound is as likely prose as a name and nothing says which word opens it —
  `operation-buffered`, `operation-specific`, `#2-operation-vocabulary`, and
  `scope_operation_and_qualifier` are all ordinary, so those positions fall back
  to the surface-noun rule;
- `op` in trailing position, which is the navigation filter's inner operand on
  the wire (`Exists.op`, `inner_op`, `root_op`) rather than a query.

A retired phrase counts across the line break a wrapped document puts in the
middle of it.

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
- the URL text of every host outside this repository, which no edit here can
  change; a URL under the repository's own host is scanned, because a canonical
  schema ``$id`` is a name this repository chooses;
- the handful of LIVE spellings a compound rule reads as retired ones, listed in
  ``_LIVE_SPELLING_WORDS``;
- this module's own test file, whose fixtures spell the retired phrases.
"""

from __future__ import annotations

import bisect
import re
import subprocess
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

# Where a whole word or identifier starts. The second lookbehind is what makes
# it a START: snake_case and kebab_case carry no signal for which of their words
# opens a compound, so an occurrence one joiner deep (`mixed_op_flush`,
# `scope_operation_and_qualifier`) is a continuation of the name around it.
_TOKEN_START = rf"{_LEFT}(?<![A-Za-z0-9][_-])"

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

# The camel compound's continuation: the rest of the word the stem's hump opens,
# however that word is cased, so `OperationTree`, `OperationURL`, and
# `OperationTreeBuilder` each report the whole compound they spell.
_CAMEL_TAIL = r"[A-Z][A-Za-z0-9]*"


def _camel_first_word(word: str) -> str:
    """*word* where a camelCase compound begins.

    A hump bounds a word the way punctuation does, so the capitalized spelling
    opens a compound wherever it sits inside an identifier (`myOperationTree`);
    the lowercase spelling opens one only where the identifier itself starts.
    """
    return f"(?:{_LEFT}[{word[0]}{word[0].upper()}]|{word[0].upper()}){word[1:]}"


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
    "model",
    "models",
    "runtime",
    "runtimes",
    "ast",
    "ir",
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
# retired module, package, and schema all abbreviate it; `m-op-list` (a live
# module) stays legal because the abbreviation there opens no name of its own
# and `list` is no surface noun.
_QUERY_STEM_WORDS = ("operations", "operation", "op")
_QUERY_STEMS = "|".join(_QUERY_STEM_WORDS)

# The trailing-position patterns use these instead, because a bare `op` after a
# position word is the navigation filter's inner operand (`inner_op`,
# `Exists.op`) — a live wire spelling — not a query named as an operation.
_QUERY_FULL_STEM_WORDS = ("operations", "operation")
_QUERY_FULL_STEMS = "|".join(_QUERY_FULL_STEM_WORDS)

# The joiner that makes an identifier out of the stem the compound opens. `-`
# rides along only for the abbreviation, which never appears in prose: the full
# stem's hyphenated forms are ordinary English ("operation-buffered mutation",
# "operation-specific roles"), while `op-` opens no English word at all.
_QUERY_OPENED_IDENTIFIER = r"(?:op[_/-]|operations?[_/])"

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


# camelCase compounds, derived from the SAME word lists as the spaced and joined
# patterns so the camel coverage can never drift from them. The stems keep their
# plural, so `OperationsTree` is caught alongside `OperationTree`.
_QUERY_CAMEL_FULL_STEMS = "|".join(_camel_first_word(stem) for stem in _QUERY_FULL_STEM_WORDS)
_QUERY_CAMEL_ABBREVIATED_STEM = _camel_first_word("op")
_QUERY_CAMEL_CONNECTIVE = rf"(?:{'|'.join(word.capitalize() for word in _QUERY_CONNECTIVE_WORDS)})?"
_QUERY_CAMEL_SURFACE = "|".join(word.capitalize() for word in _QUERY_SURFACE_WORDS)
_QUERY_CAMEL_JOINED = "|".join(_camel_first_word(word) for word in _QUERY_JOINED_WORD_LIST)
_QUERY_CAMEL_SUBJECTS = "|".join(_camel_first_word(word) for word in _QUERY_SUBJECT_WORDS)

_RETIRED_TEMPORAL_PATTERNS = (
    re.compile(
        rf"{_LEFT}(?:business|processing){_JOIN}(?:{_TEMPORAL_NOUNS}){_RIGHT}", re.IGNORECASE
    ),
    re.compile(rf"{_LEFT}(?:business|processing)[_-](?:{_JOINED_WORDS}){_RIGHT}", re.IGNORECASE),
    re.compile(
        rf"(?:{_camel_first_word('business')}|{_camel_first_word('processing')})"
        rf"(?:{_CAMEL_WORDS}){_CAMEL_RIGHT}"
    ),
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
    # An identifier or path component the stem OPENS: whatever word follows, the
    # thing being named is called an operation.
    re.compile(rf"{_TOKEN_START}{_QUERY_OPENED_IDENTIFIER}[A-Za-z0-9]+", re.IGNORECASE),
    # The same rule in camelCase, where the hump supplies the joiner. The full
    # stem carries it wherever it sits in an identifier; the abbreviation only
    # where the identifier starts, since a trailing `Op` is the wire operand.
    re.compile(rf"(?:{_QUERY_CAMEL_FULL_STEMS}){_CAMEL_TAIL}"),
    re.compile(rf"{_LEFT}[oO]p{_CAMEL_TAIL}"),
    # An `Op` hump deeper in an identifier therefore still needs a surface noun.
    re.compile(
        rf"(?:{_QUERY_CAMEL_ABBREVIATED_STEM}){_QUERY_CAMEL_CONNECTIVE}"
        rf"(?:{_QUERY_CAMEL_SURFACE}){_CAMEL_RIGHT}"
    ),
    re.compile(rf"(?:{_QUERY_CAMEL_SUBJECTS})(?:Op|Operations?){_CAMEL_RIGHT}"),
    re.compile(rf"(?:{_QUERY_CAMEL_JOINED})(?:Operations?){_CAMEL_RIGHT}"),
    # The retired schema filename, whose `.` joiner is deliberately not in the
    # general compound pattern: an ordinary sentence break before a capitalized
    # "Schema" would otherwise match.
    re.compile(rf"{_LEFT}operation\.schema\.json", re.IGNORECASE),
    # The retired read envelope's sibling entity field. Only the identifier
    # spellings are retired — the prose phrase "target entity" describes a
    # relationship's far side and stays.
    re.compile(rf"(?:{_camel_first_word('target')})(?:Entity|_entity){_RIGHT}"),
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

# The host this repository issues names under: a canonical schema `$id` spells a
# name chosen here, so its URL is scanned like any other text.
_REPOSITORY_HOST = "parallax.dev"

# A URL some other system issued, masked before matching: no edit in this
# repository can change the vocabulary its text spells. It ends where prose
# closes it — a Markdown link's `)`, a quote, a backtick, an angle bracket — so
# what a document writes AROUND a link is still repository vocabulary.
_URL = re.compile(
    rf"\b[a-z][a-z0-9+.-]*://"
    rf"(?!(?:[a-z0-9-]+\.)*{re.escape(_REPOSITORY_HOST)}(?![a-z0-9.-]))"
    rf"[^\s<>()\[\]\"'`]+"
)

# Spellings a compound rule reads as retired ones although each names something
# live: the `m-op-list` module's Python scope `parallax.core.op_list`, the
# command graph's own operation vocabulary in `gate_graph`, and the .NET
# exception name that session research cites. Masked the way a URL is.
_LIVE_SPELLING_WORDS = ("op_list", "OPERATION_TOKENS", "InvalidOperationException")
_LIVE_SPELLINGS = re.compile(
    rf"{_LEFT}(?:{'|'.join(_LIVE_SPELLING_WORDS)})(?![A-Za-z0-9_-])", re.IGNORECASE
)

# The masking character. It is not alphanumeric, so it bounds a phrase the same
# way punctuation does, and it is not a joiner, so masked text can never become
# the middle of a compound that spans it.
_MASK = "\x00"

# A line opening a block that exists to NAME retired spellings; every line of the
# block is exempt. A `_Avoid_` line is exempt on its own.
_EXEMPT_BLOCK_OPENERS = ("Prior art:", "| Retired |")
_EXEMPT_LINE_OPENER = "_Avoid_"

# Every source kind participates except these, and they are excluded by what
# they are rather than by suffix hygiene: an image carries no text, and a
# lockfile's names are chosen by a package registry, exactly like a URL's.
_UNSCANNED_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2"}
_GENERATED_NAMES = {"uv.lock", "pnpm-lock.yaml", "package-lock.json", "yarn.lock"}

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


def _is_vocabulary_surface(relative: str) -> bool:
    if relative in _EXEMPT_FILES:
        return False
    if any(relative == tree or relative.startswith(f"{tree}/") for tree in _EXEMPT_TREES):
        return False
    name = relative.rsplit("/", 1)[-1]
    return name not in _GENERATED_NAMES and Path(name).suffix.lower() not in _UNSCANNED_SUFFIXES


def scanned_files(root: Path) -> Iterator[Path]:
    """Every active-source file under *root* the deny-list applies to.

    Active is git's own view of the working tree — tracked files plus untracked
    ones it does not ignore. Asking git rather than walking the tree is what
    keeps caches, virtualenvs, build outputs, and workflow artifacts out without
    enumerating them, and what keeps a source in, whatever its suffix and however
    deep in a dot-directory it lives.

    Raises ``subprocess.CalledProcessError`` when *root* is not a git working
    tree, since then no answer would be trustworthy.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for relative in sorted(entry for entry in listing.split("\0") if entry):
        if not _is_vocabulary_surface(relative):
            continue
        path = root / relative
        if path.is_file():
            yield path


def _applicable_families(relative_path: str) -> tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]:
    directories = relative_path.split("/")[:-1]
    if _TEMPORAL_EXEMPT_DIR_NAME in directories:
        return tuple(entry for entry in _RETIRED_FAMILIES if entry[0] != "temporal")
    return _RETIRED_FAMILIES


def _blanked(match: re.Match[str]) -> str:
    return _MASK * len(match.group(0))


def _masked(text: str) -> str:
    """*text* with every exempt line, foreign URL, and live spelling ``_MASK``ed.

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
            masked.append(_LIVE_SPELLINGS.sub(_blanked, _URL.sub(_blanked, line)))
    return "\n".join(masked)


def _retired_spellings(patterns: tuple[re.Pattern[str], ...], text: str) -> Iterator[re.Match[str]]:
    """Each retired spelling *patterns* finds in *text*, once per site.

    Several patterns of one family read the same compound from different sides —
    the identifier rule and the surface-noun rule both name `op_algebra` — and
    one site is one violation.
    """
    seen: set[tuple[int, int]] = set()
    for pattern in patterns:
        for match in pattern.finditer(text):
            if match.span() not in seen:
                seen.add(match.span())
                yield match


def check_text(relative_path: str, text: str) -> list[str]:
    """Every retired-vocabulary violation in *text* (empty ⇒ clean).

    A ``_Avoid_`` line, every line of a paragraph opening ``Prior art:``, every
    row of a table whose first header cell is ``Retired``, every foreign URL, and
    every live spelling are masked before matching: each names something this
    repository does not choose or has not retired. Matching runs over the whole
    document rather than line by line, so a phrase wrapped across a line break is
    caught at the line it starts on.
    """
    scanned = _masked(text)
    line_starts = [0]
    for index, character in enumerate(scanned):
        if character == "\n":
            line_starts.append(index + 1)
    violations: list[str] = []
    for family, patterns in _applicable_families(relative_path):
        for match in _retired_spellings(patterns, scanned):
            lineno = bisect.bisect_right(line_starts, match.start())
            phrase = " ".join(match.group(0).split())
            violations.append(f"{relative_path}:{lineno}: retired {family} vocabulary {phrase!r}")
    return violations


def check_path(relative_path: str) -> list[str]:
    """Every retired-vocabulary violation in *relative_path* itself.

    A module, a schema, and a corpus case name their subject in the filename, so
    the path is vocabulary surface in its own right and a retired spelling can
    survive there while every line of the file is clean.
    """
    violations: list[str] = []
    for family, patterns in _applicable_families(relative_path):
        for match in _retired_spellings(patterns, relative_path):
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
    *argv[0]* is not a directory or not a git working tree).
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
    try:
        paths = list(scanned_files(root))
    except subprocess.CalledProcessError as error:
        print(f"not a git working tree: {root} ({error.stderr.strip()})", file=sys.stderr)
        return 2
    for path in paths:
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
