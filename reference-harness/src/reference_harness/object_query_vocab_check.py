"""Assert `m-object-query.md`'s prose closed vocabularies equal the matching
`object-query.schema.json` definitions (the Object Query two-home consistency
check)::

    uv run python -m reference_harness.object_query_vocab_check core/spec

Two Object Query vocabularies are documented in TWO places each that must never
drift apart — the normative prose in ``core/spec/m-object-query.md`` and the
canonical schema:

1. the **Temporal Selection variants**, from the ``temporal`` section's table
   against the branches of the schema's ``$defs.temporalSelection`` union;
2. the **Null Placement values**, from the ``orderBy`` section's Sort Key
   sentence against ``$defs.sortKey.properties.nulls``'s ``enum``.

Both arrived with the Object Query as genuinely new closed vocabularies, and
adding a ``$def`` is otherwise checked only for meta-schema validity: a variant
the schema admits but no prose documents, or prose documenting one the schema
refuses, would be invisible to every other gate. A schema union missing a
variant the prose already documents is the safety-critical direction, since a
query spelling it would fail SCHEMA validation regardless of whether every
implementation realized it correctly.

Parsing the prose. The Temporal Selection variants are the leading inline-code
span of each body row of the one markdown table in the ``temporal`` section;
that column is the variant's own tag, and the row's remaining cells are its
encoding and meaning. The Null Placement values are the inline-code spans of the
parenthesis that follows the ``Null Placement`` marker in the ``orderBy``
section's Sort Key sentence, which names the two placements and then repeats one
as the default.

Deriving the schema side. Neither vocabulary is read from a literal list here.
A Temporal Selection variant is the single ``required`` member of the branch
each ``oneOf`` entry references, so a new branch enters this check the moment it
is added to the union; a Null Placement value is the ``nulls`` ``enum`` itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .paths import schemas_dir
from .schemas import load_json

__all__ = [
    "ObjectQueryVocabMismatch",
    "check",
    "main",
    "prose_null_placements",
    "prose_temporal_selection_variants",
    "schema_null_placements",
    "schema_temporal_selection_variants",
]

_HEADING = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)

# A table body row's own leading inline-code span: the first cell's code, after
# the opening pipe. The header (`| Selection | ...`) and the delimiter row
# (`|---|`) carry no inline code, so neither matches.
_TABLE_ROW_CODE = re.compile(r"^\|\s*`([A-Za-z][A-Za-z0-9]*)`\s*\|", re.MULTILINE)

_INLINE_CODE = re.compile(r"`([^`]+)`")

_TEMPORAL_HEADING_MARKER = "Temporal Selection per dimension"
_ORDER_BY_HEADING_MARKER = "Sort Keys"
_NULL_PLACEMENT_MARKER = "Null Placement"


class ObjectQueryVocabMismatch(ValueError):
    """A prose and schema Object Query vocabulary disagree, or a home is malformed."""


def _section(markdown: str, heading_contains: str) -> str:
    """The body text between the first heading containing *heading_contains*
    and the next heading of any level (or end of document)."""
    headings = list(_HEADING.finditer(markdown))
    for index, heading in enumerate(headings):
        if heading_contains in heading.group(0):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
            return markdown[start:end]
    raise ObjectQueryVocabMismatch(
        f"no heading containing {heading_contains!r} found in m-object-query.md"
    )


def prose_temporal_selection_variants(markdown: str) -> set[str]:
    """The Temporal Selection variants `m-object-query.md`'s prose documents.

    Raises `ObjectQueryVocabMismatch` when the section carries no such table,
    which means the parsing anchor drifted rather than that the union emptied.
    """
    section = _section(markdown, _TEMPORAL_HEADING_MARKER)
    variants = set(_TABLE_ROW_CODE.findall(section))
    if not variants:
        raise ObjectQueryVocabMismatch(
            f"the {_TEMPORAL_HEADING_MARKER!r} section documents no Temporal Selection table"
        )
    return variants


def prose_null_placements(markdown: str) -> set[str]:
    """The Null Placement values `m-object-query.md`'s prose documents.

    Reads the parenthesis that follows the ``Null Placement`` marker in the
    Sort Key sentence: it names both placements and then repeats one as the
    default, so the parsed set is the two placements. Raises
    `ObjectQueryVocabMismatch` when the marker or its parenthesis is missing, or
    when the parenthesis carries no inline code.
    """
    section = _section(markdown, _ORDER_BY_HEADING_MARKER)
    if _NULL_PLACEMENT_MARKER not in section:
        raise ObjectQueryVocabMismatch(
            f"no {_NULL_PLACEMENT_MARKER!r} marker found in the "
            f"{_ORDER_BY_HEADING_MARKER!r} section"
        )
    rest = section[section.index(_NULL_PLACEMENT_MARKER) :]
    opened = rest.find("(")
    closed = rest.find(")")
    if opened == -1 or closed < opened:
        raise ObjectQueryVocabMismatch(
            "the Null Placement sentence carries no parenthesized value list"
        )
    values = set(_INLINE_CODE.findall(rest[opened:closed]))
    if not values:
        raise ObjectQueryVocabMismatch("the Null Placement value list names no placement")
    return values


def _defs(schema: dict[str, object]) -> dict[str, object]:
    defs = schema.get("$defs")
    if not isinstance(defs, dict):
        raise ObjectQueryVocabMismatch("object-query.schema.json declares no $defs")
    return defs


def schema_temporal_selection_variants(schema: dict[str, object]) -> set[str]:
    """The Temporal Selection variants `object-query.schema.json` admits.

    Each ``$defs.temporalSelection`` ``oneOf`` branch references a closed
    single-key object, and that key — the branch's sole ``required`` member — is
    the variant's tag. Deriving it from the union rather than from a literal
    list is what makes a newly added branch fail this check until the prose
    documents it.
    """
    defs = _defs(schema)
    selection = defs.get("temporalSelection")
    branches = selection.get("oneOf") if isinstance(selection, dict) else None
    if not isinstance(branches, list) or not branches:
        raise ObjectQueryVocabMismatch(
            "object-query.schema.json declares no $defs.temporalSelection oneOf union"
        )
    variants: set[str] = set()
    for branch in branches:
        ref = branch.get("$ref") if isinstance(branch, dict) else None
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ObjectQueryVocabMismatch(
                f"a temporalSelection branch is not a local $ref: {branch!r}"
            )
        target = defs.get(ref.removeprefix("#/$defs/"))
        required = target.get("required") if isinstance(target, dict) else None
        if not isinstance(required, list) or len(required) != 1:
            raise ObjectQueryVocabMismatch(
                f"the temporalSelection branch {ref!r} does not require exactly one member"
            )
        variants.add(str(required[0]))
    return variants


def schema_null_placements(schema: dict[str, object]) -> set[str]:
    """The Null Placement values `object-query.schema.json` admits, from a Sort
    Key's ``nulls`` enum."""
    defs = _defs(schema)
    sort_key = defs.get("sortKey")
    properties = sort_key.get("properties") if isinstance(sort_key, dict) else None
    nulls = properties.get("nulls") if isinstance(properties, dict) else None
    enum = nulls.get("enum") if isinstance(nulls, dict) else None
    if not isinstance(enum, list) or not enum:
        raise ObjectQueryVocabMismatch(
            "object-query.schema.json declares no $defs.sortKey.properties.nulls enum"
        )
    return {str(value) for value in enum}


def _vocabulary_errors(vocabulary: str, prose: set[str], declared: set[str]) -> list[str]:
    """Both drift directions between one vocabulary's two homes."""
    errors: list[str] = []
    missing_from_schema = sorted(prose - declared)
    missing_from_prose = sorted(declared - prose)
    if missing_from_schema:
        errors.append(
            f"{vocabulary}: documented in m-object-query.md but absent from "
            f"object-query.schema.json: {missing_from_schema}"
        )
    if missing_from_prose:
        errors.append(
            f"{vocabulary}: declared in object-query.schema.json but undocumented in "
            f"m-object-query.md: {missing_from_prose}"
        )
    return errors


def check(object_query_markdown: str, schema: dict[str, object]) -> list[str]:
    """Every inconsistency between the prose and schema homes of BOTH the
    Temporal Selection variants and the Null Placement values (empty ⇒
    consistent).

    Propagates `ObjectQueryVocabMismatch` when a home is missing or malformed;
    the returned list covers only set-level disagreement between parsed homes.
    """
    return _vocabulary_errors(
        "Temporal Selection variants",
        prose_temporal_selection_variants(object_query_markdown),
        schema_temporal_selection_variants(schema),
    ) + _vocabulary_errors(
        "Null Placement values",
        prose_null_placements(object_query_markdown),
        schema_null_placements(schema),
    )


def main(argv: list[str]) -> int:
    """CLI entry point: compare `m-object-query.md` under the spec directory
    *argv[0]* against `object-query.schema.json`.

    Exit codes: 0 — both vocabularies agree; 1 — a vocabulary drifted or a home
    is malformed; 2 — usage error (argument count, or no `m-object-query.md`
    under *argv[0]*).
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.object_query_vocab_check <spec-dir>",
            file=sys.stderr,
        )
        return 2
    spec_dir = Path(argv[0])
    object_query_path = spec_dir / "m-object-query.md"
    if not object_query_path.is_file():
        print(f"not a file: {object_query_path}", file=sys.stderr)
        return 2

    object_query_markdown = object_query_path.read_text(encoding="utf-8")
    schema = load_json(schemas_dir(spec_dir) / "object-query.schema.json")

    try:
        errors = check(object_query_markdown, schema)
    except ObjectQueryVocabMismatch as exc:
        print(f"object-query vocabulary check FAILED: {exc}", file=sys.stderr)
        return 1

    if errors:
        print(
            f"object-query vocabulary check FAILED ({len(errors)} mismatch(es)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "object-query vocabulary check OK: prose and schema Temporal Selection "
        "variants and Null Placement values match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
