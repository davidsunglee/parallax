"""Deny-list gate: no retired vocabulary in active sources::

    uv run python -m reference_harness.retired_vocab_check <repo-root>

Two vocabularies are retired repository-wide. A retired spelling survives
wherever nobody happens to look, so the deny-list enumerates both mechanically
over every active source file — its text and its repository-relative path, since
a module, a schema, and a corpus case each carry vocabulary in their filename.
Active is git's own view of the working tree: every tracked file plus every
untracked one it does not ignore, whatever its directory or suffix.

**Execution log.** ADR 0060 supersedes ADR 0055: execution observability is a
transient event stream a Provider receives, never a record a result retains, and
the module that owned the retained record is retired in favor of
`m-execution-lifecycle`. Only the IDENTIFIER-shaped spellings are retired — the
module slug, its scope name, and the camel type — because the compound names one
retired subject wherever it is written, unlike the temporal family below whose
stems are ordinary English.

**Temporal.** The root glossary's `_Avoid_` registry retires the
Reladomo-derived temporal spellings — business time/date, processing time/date,
effective date, system date, and the business/processing dimension family — in
favor of Valid Time / Transaction Time, and retires the camelCase dimension
spellings `validTime` / `transactionTime` in favor of the kebab-case enumerated
values `valid-time` / `transaction-time`.

The temporal deny-list matches whole retired PHRASES rather than bare words,
because its stems are ordinary English. What makes a phrase retired depends on
where it is written:

- in prose, the stem counts only beside a listed temporal noun, so "business
  key" and "business/developer name" stay while "business date" and "the
  business/processing dimension pair" do not;
- a handful of position words are retired only where `-` or `_` joins them to
  the stem, since their spaced forms are ordinary English: `business-from` and
  `processing-latest` are names, "separates the business from" is a sentence;
- a camelCase hump bounds a word the way punctuation does, so a capitalized stem
  counts wherever it sits inside an identifier: `entityBusinessDate` and
  `businessFromValue` are the compound their hump spells.

What the compound rules deliberately do not decide is the bare stem in prose,
because this repository spells the same word for live subjects: it stays legal
in every sense that is not temporal ("the business key", "processing continues
with the next statement").

A retired phrase counts across the line break a wrapped document puts in the
middle of it.

Allow-list (explicitly labeled historical / prior-art / rejection text):

- ``docs/research/reladomo/**`` — prior-art notes keep the vocabulary of the
  system they describe (other research documents are active prose and are
  scanned);
- every ``adr`` directory. A decision record preserves the vocabulary current
  when it was written, whether or not the decision still binds: ADR 0055's whole
  subject is the retained Execution Log a later record superseded, while ADR
  0021 still binds and states its required temporal terminate in the business /
  processing terms retired since. Neither family is scanned there;
- ``core/compatibility/descriptor-errors/`` — negative-test fixtures exist to
  spell the retired forms so serde provably rejects them;
- glossary ``_Avoid_`` lines, the labeled ``Prior art:`` paragraph, and a table
  whose first header cell is ``Retired`` — they name the retired spellings in
  order to retire them;
- the URL text of every host outside this repository, which no edit here can
  change; a URL under the repository's own host is scanned, because a canonical
  schema ``$id`` is a name this repository chooses;
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


def _camel_first_word(word: str) -> str:
    """*word* where a camelCase compound begins.

    A hump bounds a word the way punctuation does, so the capitalized spelling
    opens a compound wherever it sits inside an identifier (`entityBusinessDate`);
    the lowercase spelling opens one only where the identifier itself starts.
    """
    return f"(?:{_LEFT}[{word[0]}{word[0].upper()}]|{word[0].upper()}){word[1:]}"


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

# The retired execution-log vocabulary: the module ADR 0060 superseded, its
# Python scope, and the record type it owned. Two patterns suffice where the
# temporal family needs many, because the compound is a NAME rather than an
# English phrase — `execution` opens it and `log` closes it, in prose, in a
# slug, in snake_case, and across a wrapped line alike. The live spelling it
# makes room for is `execution lifecycle`, which shares only the first word.
_RETIRED_EXECUTION_LOG_PATTERNS = (
    re.compile(rf"{_LEFT}execution{_JOIN}logs?{_RIGHT}", re.IGNORECASE),
    re.compile(rf"ExecutionLogs?{_CAMEL_RIGHT}"),
)

_RETIRED_FAMILIES = (
    ("temporal", _RETIRED_TEMPORAL_PATTERNS),
    ("execution log", _RETIRED_EXECUTION_LOG_PATTERNS),
)

# The host this repository issues names under: a canonical schema `$id` spells a
# name chosen here, so its URL is scanned like any other text.
_REPOSITORY_HOST = "parallax.dev"

# A URL some other system issued, masked before matching: no edit in this
# repository can change the vocabulary its text spells. It ends where prose
# closes it — a Markdown link's `)`, a quote, a backtick, an angle bracket — so
# what a document writes AROUND a link is still repository vocabulary. A host is
# case-insensitive, so the repository's own host is recognized however it is
# written; the guard after it keeps a look-alike neighbour (`parallax.devil.io`)
# foreign.
_URL = re.compile(
    rf"\b[a-z][a-z0-9+.-]*://"
    rf"(?!(?i:(?:[a-z0-9-]+\.)*{re.escape(_REPOSITORY_HOST)})(?![A-Za-z0-9.-]))"
    rf"[^\s<>()\[\]\"'`]+"
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

# A directory whose documents preserve the vocabulary current when they were
# written, including spellings retired since: a record that still binds is
# written in the terms of its own day no less than one a later record
# superseded. No retired family applies there.
_DECISION_RECORD_DIR_NAME = "adr"

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


def _is_decision_record(relative_path: str) -> bool:
    return _DECISION_RECORD_DIR_NAME in relative_path.split("/")[:-1]


def _blanked(match: re.Match[str]) -> str:
    return _MASK * len(match.group(0))


def _masked(text: str) -> str:
    """*text* with every exempt line and foreign URL ``_MASK``ed.

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
            masked.append(_URL.sub(_blanked, line))
    return "\n".join(masked)


def _retired_spellings(patterns: tuple[re.Pattern[str], ...], text: str) -> Iterator[re.Match[str]]:
    for pattern in patterns:
        yield from pattern.finditer(text)


def check_text(relative_path: str, text: str) -> list[str]:
    """Every retired-vocabulary violation in *text* (empty ⇒ clean).

    A decision record is exempt outright. Within every other document a
    ``_Avoid_`` line, every line of a paragraph opening ``Prior art:``, every row
    of a table whose first header cell is ``Retired``, and every foreign URL are
    masked before matching: each names something this repository does not choose
    or has not retired. Matching runs over the whole document rather than line by
    line, so a phrase wrapped across a line break is caught at the line it starts
    on.
    """
    if _is_decision_record(relative_path):
        return []
    scanned = _masked(text)
    line_starts = [0]
    for index, character in enumerate(scanned):
        if character == "\n":
            line_starts.append(index + 1)
    violations: list[str] = []
    for family, patterns in _RETIRED_FAMILIES:
        for match in _retired_spellings(patterns, scanned):
            lineno = bisect.bisect_right(line_starts, match.start())
            phrase = " ".join(match.group(0).split())
            violations.append(f"{relative_path}:{lineno}: retired {family} vocabulary {phrase!r}")
    return violations


def check_path(relative_path: str) -> list[str]:
    """Every retired-vocabulary violation in *relative_path* itself.

    A module, a schema, and a corpus case name their subject in the filename, so
    the path is vocabulary surface in its own right and a retired spelling can
    survive there while every line of the file is clean. A decision record is
    exempt, exactly as its text is.
    """
    if _is_decision_record(relative_path):
        return []
    violations: list[str] = []
    for family, patterns in _RETIRED_FAMILIES:
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

    Exit codes: 0 — no retired vocabulary of any family on any scanned
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

    print("retired-vocabulary check OK: no retired vocabulary in active sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
