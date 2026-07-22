"""Assert the neutral-type vocabulary's three homes agree (the closed-vocabulary
three-home consistency check)::

    uv run python -m reference_harness.neutral_type_vocab_check core/spec

The neutral-type variant set is spelled in THREE places that nothing else
forces to agree:

1. the structured ``NeutralType`` algebra block in ``core/spec/m-core.md``
   (PascalCase variants inside the sole fenced ``text`` block of the
   ``NeutralType`` algebra section — a fence moved to another section, or a
   duplicate stale fence beside the real one, fails loudly instead of being
   silently accepted);
2. the "Type spellings" table in ``core/spec/m-descriptor.md`` (the canonical
   lowercase wire spelling per variant, bound to the "Type spellings" section);
3. the ``neutralType`` ``pattern`` regex in ``core/schemas/metamodel.schema.json``
   (the alternation the schema phase accepts).

A variant added, removed, or renamed in one home but not the others would let
the algebra, the wire grammar, and the schema silently diverge — a model could
then pass schema validation with a type the algebra does not define, or the
spec could promise a variant no descriptor can spell. This module parses all
three homes, normalizes each to the lowercase variant-token set (``Decimal`` /
``decimal(<p>,<s>)`` / ``decimal\\(...\\)`` all normalize to ``decimal``), and
fails when any home lacks a variant another declares — so a future variant
lands in all three homes or not at all.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .paths import schemas_dir
from .schemas import load_json

__all__ = [
    "VocabMismatch",
    "check",
    "core_algebra_variants",
    "descriptor_spelling_variants",
    "main",
    "schema_pattern_variants",
]


class VocabMismatch(ValueError):
    """A neutral-type home is missing, malformed, or disagrees with the others."""


_HEADING = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)
_TEXT_FENCE = re.compile(r"```text\n(.*?)```", re.DOTALL)

# A PascalCase variant name inside the algebra block. Lowercase parameter names
# (``precision: int``) never match; ``#`` comments are stripped before matching
# so uppercase comment words never register as variants.
_ALGEBRA_VARIANT = re.compile(r"[A-Z][A-Za-z0-9]*")

# A spelling cell: one backticked lowercase token, optionally parameterized
# (``decimal(<precision>,<scale>)``).
_SPELLING_CELL = re.compile(r"`([a-z][a-z0-9]*)(?:\(.*\))?`")

# The leading token of one schema-pattern alternative (``decimal\(...`` -> ``decimal``).
_PATTERN_TOKEN = re.compile(r"^[a-z][a-z0-9]*")

_ALGEBRA_SECTION_MARKER = "`NeutralType` algebra"
_TYPE_SPELLINGS_MARKER = "Type spellings"


def _section(markdown: str, heading_contains: str, source: str) -> str:
    """The body text between the first heading containing *heading_contains*
    and the next heading of any level (or end of document)."""
    headings = list(_HEADING.finditer(markdown))
    for index, heading in enumerate(headings):
        if heading_contains in heading.group(0):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
            return markdown[start:end]
    raise VocabMismatch(f"no heading containing {heading_contains!r} found in {source}")


def core_algebra_variants(core_markdown: str) -> set[str]:
    """The lowercase variant tokens the `m-core.md` `NeutralType` algebra block declares.

    The block is bound to its owning section: exactly one candidate ``text``
    fence naming ``NeutralType`` must sit under the `NeutralType` algebra
    heading. Raises `VocabMismatch` when the section is missing, holds zero
    candidate fences (e.g. the block moved elsewhere) or more than one (e.g. a
    stale duplicate), or the sole fence is malformed or declares no variants.
    """
    section = _section(core_markdown, _ALGEBRA_SECTION_MARKER, "m-core.md")
    candidates = [
        fence.group(1) for fence in _TEXT_FENCE.finditer(section) if "NeutralType" in fence.group(1)
    ]
    if not candidates:
        raise VocabMismatch(
            "no fenced NeutralType algebra block found in the m-core NeutralType algebra "
            "section (a fence outside its owning section does not count)"
        )
    if len(candidates) > 1:
        raise VocabMismatch(
            f"{len(candidates)} fenced NeutralType blocks found in the m-core NeutralType "
            "algebra section; exactly one must own the vocabulary"
        )
    _, separator, right_side = candidates[0].partition("=")
    if not separator:
        raise VocabMismatch("the m-core NeutralType block carries no `=` union body")
    uncommented = "\n".join(line.split("#", 1)[0] for line in right_side.splitlines())
    variants = {name.lower() for name in _ALGEBRA_VARIANT.findall(uncommented)}
    if not variants:
        raise VocabMismatch("the m-core NeutralType block declares no variants")
    return variants


def descriptor_spelling_variants(descriptor_markdown: str) -> set[str]:
    """The lowercase spelling tokens the `m-descriptor.md` "Type spellings" table declares.

    Raises `VocabMismatch` when the "Type spellings" section is missing or its
    table carries no spelling rows.
    """
    section = _section(descriptor_markdown, _TYPE_SPELLINGS_MARKER, "m-descriptor.md")
    variants: set[str] = set()
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) != 2:
            continue
        match = _SPELLING_CELL.fullmatch(cells[1])
        if match:
            variants.add(match.group(1))
    if not variants:
        raise VocabMismatch("no spelling rows found in the m-descriptor Type spellings table")
    return variants


def schema_pattern_variants(schema: object) -> set[str]:
    """The lowercase variant tokens the schema's `neutralType` pattern alternation admits.

    Raises `VocabMismatch` when the schema document root is not a JSON object,
    the schema declares no `$defs.neutralType.pattern` string, the pattern is
    not a fully anchored alternation, or an alternative carries no leading
    lowercase token.
    """
    if not isinstance(schema, dict):
        raise VocabMismatch("the metamodel schema document root is not a JSON object")
    defs = schema.get("$defs")
    neutral_type = defs.get("neutralType") if isinstance(defs, dict) else None
    pattern = neutral_type.get("pattern") if isinstance(neutral_type, dict) else None
    if not isinstance(pattern, str):
        raise VocabMismatch("metamodel.schema.json declares no $defs.neutralType.pattern")
    if not (pattern.startswith("^(") and pattern.endswith(")$")):
        raise VocabMismatch(
            f"the neutralType pattern is not a fully anchored alternation: {pattern!r}"
        )
    variants: set[str] = set()
    for alternative in pattern[2:-2].split("|"):
        match = _PATTERN_TOKEN.match(alternative)
        if match is None:
            raise VocabMismatch(f"unparseable neutralType pattern alternative: {alternative!r}")
        variants.add(match.group(0))
    if not variants:
        raise VocabMismatch("the neutralType pattern admits no variants")
    return variants


def check(core_markdown: str, descriptor_markdown: str, schema: dict[str, object]) -> list[str]:
    """Every inconsistency between the three variant homes (empty ⇒ consistent).

    Propagates `VocabMismatch` from the three extractors when any home is
    missing or malformed; the returned list covers only set-level disagreement
    between successfully parsed homes.
    """
    homes = {
        "the m-core NeutralType algebra block": core_algebra_variants(core_markdown),
        "the m-descriptor Type spellings table": descriptor_spelling_variants(descriptor_markdown),
        "the metamodel.schema.json neutralType pattern": schema_pattern_variants(schema),
    }
    union = set().union(*homes.values())
    errors: list[str] = []
    for variant in sorted(union):
        missing = [name for name, variants in homes.items() if variant not in variants]
        if missing:
            errors.append(f"variant {variant!r} is missing from: {', '.join(missing)}")
    return errors


def main(argv: list[str]) -> int:
    """CLI entry point: parse the three homes under the spec directory *argv[0]*
    (schema location derived via `schemas_dir`) and report agreement on stdout /
    disagreement on stderr.

    Exit codes: 0 — the three homes agree; 1 — a home inside a readable input
    is missing or malformed (`VocabMismatch`, schema JSON that does not parse,
    or a schema document whose root is not a JSON object; reported, never
    raised to the caller) or the homes disagree; 2 — usage error, or an input
    file (a spec markdown or the metamodel schema) is missing or unreadable.
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.neutral_type_vocab_check <spec-dir>",
            file=sys.stderr,
        )
        return 2
    spec_dir = Path(argv[0])
    core_path = spec_dir / "m-core.md"
    descriptor_path = spec_dir / "m-descriptor.md"
    texts: list[str] = []
    for path in (core_path, descriptor_path):
        if not path.is_file():
            print(f"not a file: {path}", file=sys.stderr)
            return 2
        try:
            texts.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"unreadable spec file {path}: {exc}", file=sys.stderr)
            return 2
    core_markdown, descriptor_markdown = texts

    try:
        schema_path = schemas_dir(spec_dir) / "metamodel.schema.json"
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        schema = load_json(schema_path)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"unreadable schema file {schema_path}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"malformed schema JSON in {schema_path}: {exc}", file=sys.stderr)
        return 1

    try:
        if not isinstance(schema, dict):
            raise VocabMismatch(
                f"malformed schema JSON in {schema_path}: the document root is not a JSON object"
            )
        errors = check(core_markdown, descriptor_markdown, schema)
    except VocabMismatch as exc:
        print(f"neutral-type vocabulary check FAILED: {exc}", file=sys.stderr)
        return 1

    if errors:
        print(
            f"neutral-type vocabulary check FAILED ({len(errors)} mismatch(es)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "neutral-type vocabulary check OK: the m-core algebra, m-descriptor spellings, "
        "and schema pattern agree"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
