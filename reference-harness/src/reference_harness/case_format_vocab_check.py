"""Assert `m-case-format.md`'s prose closed vocabularies equal the matching
`compatibility-case.schema.json` enums (the closed-vocabulary two-home
consistency check)::

    uv run python -m reference_harness.case_format_vocab_check core/spec

Two case-format vocabularies are documented in TWO places each that must never
drift apart — the normative prose in ``core/spec/m-case-format.md`` and an
``enum`` in ``compatibility-case.schema.json``:

1. ``then.rejectedRule``, from the "Rejected cases" section against the
   schema's ``properties.then.properties.rejectedRule`` enum;
2. a scenario step's ``expectError``, from the "Per-step lifecycle observables"
   section against the per-step enum at
   ``properties.when.properties.scenario.items.properties.expectError`` — the
   ``expectError`` position is on the STEP shape, not under ``then``, so it is
   a different schema path rather than a second ``then`` property.

A schema `enum` missing an entry the prose already documents is a
safety-critical gap, since a case pinning that value would fail SCHEMA
validation regardless of whether every implementation classified it correctly.
This is a mechanical guard: it parses both sides of both vocabularies and
asserts set equality, independent of either author remembering to update the
other.

Parsing the prose. The "Rejected cases" section names each rule in one of two
shapes. **Operation** / **Write** / **Subtype-write** rules are each a
top-level bullet whose FIRST inline-code span is the rule name (` - `rule-name`
— description`); this module reads the rule name at the start of every such
bullet line. **Model** rules are instead named inline, comma-separated, inside
one prose paragraph opening "**Model** rules (...)"; this module extracts
every inline-code span in that one paragraph, excluding a module reference
(`` `m-inheritance` ``, `` `m-op-algebra` ``, …) or a dotted field reference
(`` `when.model` ``) — neither of which is ever a `rejectedRule` value. The
``expectError`` vocabulary is instead one NESTED bullet list under the
"Per-step lifecycle observables" section's ``expectError`` bullet; this module
reads the first inline-code span of every nested bullet under it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from .paths import schemas_dir
from .schemas import load_json

__all__ = [
    "VocabMismatch",
    "main",
    "prose_expect_errors",
    "prose_rejected_rules",
    "schema_expect_errors",
    "schema_rejected_rules",
]

# A rule identifier: lower-kebab-case, never a module reference (`m-xxx`) and
# never containing a dot (a `when.foo` field reference) — both appear as
# OTHER inline-code spans in the same prose this module parses.
_RULE_NAME = re.compile(r"[a-z][a-z0-9-]*")

# A top-level bullet's own rule name: the FIRST inline-code span right after
# the bullet dash (a bullet's description may name other rules/modules in
# later backticked spans, which this deliberately ignores).
_BULLET_RULE = re.compile(r"^-\s*`([a-z][a-z0-9-]*)`", re.MULTILINE)

# A NESTED bullet's own code: the first inline-code span after an INDENTED
# bullet dash. The owning bullet's own prose names other backticked spans
# (`m-db-error`, `errorClass`, …), none of which starts a nested bullet.
_NESTED_BULLET_CODE = re.compile(r"^\s+-\s*`([a-z][a-z0-9-]*)`", re.MULTILINE)

# The start of the bullet FOLLOWING a top-level bullet's whole body.
_TOP_LEVEL_BULLET = re.compile(r"^-\s", re.MULTILINE)

_HEADING = re.compile(r"^#{1,6}\s+.*$", re.MULTILINE)

_REJECTED_HEADING_MARKER = "Rejected cases"
_MODEL_RULES_MARKER = "**Model** rules"
_MODEL_RULES_END_MARKER = "invariant)."

_OBSERVABLES_HEADING_MARKER = "Per-step lifecycle observables"
_EXPECT_ERROR_MARKER = "- **`expectError`**"

_EXPECT_ERROR_SCHEMA_PATH = (
    "properties",
    "when",
    "properties",
    "scenario",
    "items",
    "properties",
    "expectError",
)


class VocabMismatch(ValueError):
    """A prose and schema case-format vocabulary disagree, or a home is malformed."""


def _section(markdown: str, heading_contains: str) -> str:
    """The body text between the first heading containing *heading_contains*
    and the next heading of any level (or end of document)."""
    headings = list(_HEADING.finditer(markdown))
    for index, heading in enumerate(headings):
        if heading_contains in heading.group(0):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
            return markdown[start:end]
    raise VocabMismatch(f"no heading containing {heading_contains!r} found in m-case-format.md")


def _bulleted_rules(section: str) -> set[str]:
    """Every top-level bullet's own rule name (Operation / Write /
    Subtype-write rules — each a `` - `rule-name` — description`` bullet)."""
    return set(_BULLET_RULE.findall(section))


def _model_rules(section: str) -> set[str]:
    """Every rule name in the one comma-separated "**Model** rules (...)"
    prose paragraph, excluding a module reference or a dotted field name."""
    if _MODEL_RULES_MARKER not in section:
        raise VocabMismatch(
            f"no {_MODEL_RULES_MARKER!r} paragraph found in the Rejected cases section"
        )
    start = section.index(_MODEL_RULES_MARKER)
    rest = section[start:]
    if _MODEL_RULES_END_MARKER not in rest:
        raise VocabMismatch(
            f"the {_MODEL_RULES_MARKER!r} paragraph never reaches "
            f"{_MODEL_RULES_END_MARKER!r} (closing citation) — parsing anchor drifted"
        )
    end = rest.index(_MODEL_RULES_END_MARKER) + len(_MODEL_RULES_END_MARKER)
    paragraph = rest[:end]
    spans = {span for span in re.findall(r"`([^`]+)`", paragraph) if _RULE_NAME.fullmatch(span)}
    return {span for span in spans if not span.startswith("m-")}


def prose_rejected_rules(markdown: str) -> set[str]:
    """The `rejectedRule` vocabulary `m-case-format.md`'s prose documents."""
    section = _section(markdown, _REJECTED_HEADING_MARKER)
    return _bulleted_rules(section) | _model_rules(section)


def prose_expect_errors(case_format_markdown: str) -> set[str]:
    """The `expectError` vocabulary `m-case-format.md`'s prose documents.

    Reads the nested bullet list under the "Per-step lifecycle observables"
    section's ``expectError`` bullet, which ends where the next TOP-LEVEL
    bullet begins. Raises `VocabMismatch` when the section or that bullet is
    missing, or when the bullet carries no nested code — each of which means
    the parsing anchor drifted rather than that the vocabulary emptied.
    """
    section = _section(case_format_markdown, _OBSERVABLES_HEADING_MARKER)
    if _EXPECT_ERROR_MARKER not in section:
        raise VocabMismatch(
            f"no {_EXPECT_ERROR_MARKER!r} bullet found in the "
            f"{_OBSERVABLES_HEADING_MARKER!r} section"
        )
    start = section.index(_EXPECT_ERROR_MARKER) + len(_EXPECT_ERROR_MARKER)
    rest = section[start:]
    following = _TOP_LEVEL_BULLET.search(rest)
    bullet = rest[: following.start()] if following else rest
    codes = set(_NESTED_BULLET_CODE.findall(bullet))
    if not codes:
        raise VocabMismatch("the expectError bullet lists no nested error codes")
    return codes


def schema_rejected_rules(schema: dict[str, object]) -> set[str]:
    """The `rejectedRule` enum `compatibility-case.schema.json` declares.

    Lives once, shared across every case shape, under the schema's top-level
    ``properties.then.properties.rejectedRule`` (the per-shape ``oneOf``
    branches only ADD shape-specific requirements — e.g. that a `rejected`
    case's `then` requires `rejectedRule` — never redeclare the enum itself).
    """
    properties = schema.get("properties", {})
    then = properties.get("then", {}) if isinstance(properties, dict) else {}
    then_properties = then.get("properties", {}) if isinstance(then, dict) else {}
    rejected_rule = (
        then_properties.get("rejectedRule") if isinstance(then_properties, dict) else None
    )
    if isinstance(rejected_rule, dict) and "enum" in rejected_rule:
        return set(rejected_rule["enum"])
    raise VocabMismatch("compatibility-case.schema.json declares no rejectedRule enum")


def schema_expect_errors(schema: dict[str, object]) -> set[str]:
    """The `expectError` enum `compatibility-case.schema.json` declares.

    Lives on the SCENARIO STEP shape rather than under ``then``: a step, not a
    case, declares the error its verb raises.
    """
    node: object = schema
    for key in _EXPECT_ERROR_SCHEMA_PATH:
        if not isinstance(node, dict):
            node = None
            break
        node = node.get(key)
    enum = node.get("enum") if isinstance(node, dict) else None
    if isinstance(enum, list):
        return {str(value) for value in enum}
    raise VocabMismatch(
        "compatibility-case.schema.json declares no expectError enum at "
        f"{'.'.join(_EXPECT_ERROR_SCHEMA_PATH)}"
    )


def _vocabulary_errors(vocabulary: str, prose: set[str], schema_enum: set[str]) -> list[str]:
    """Both drift directions between one vocabulary's two homes."""
    errors: list[str] = []
    missing_from_schema = sorted(prose - schema_enum)
    missing_from_prose = sorted(schema_enum - prose)
    if missing_from_schema:
        errors.append(
            f"{vocabulary}: documented in m-case-format.md but absent from the schema enum: "
            f"{missing_from_schema}"
        )
    if missing_from_prose:
        errors.append(
            f"{vocabulary}: declared in the schema enum but undocumented in m-case-format.md: "
            f"{missing_from_prose}"
        )
    return errors


def check(case_format_markdown: str, schema: dict[str, object]) -> list[str]:
    """Every inconsistency between the prose and schema homes of BOTH the
    `rejectedRule` and `expectError` vocabularies (empty ⇒ consistent).

    Propagates `VocabMismatch` when a home is missing or malformed; the
    returned list covers only set-level disagreement between parsed homes.
    """
    return _vocabulary_errors(
        "rejectedRule",
        prose_rejected_rules(case_format_markdown),
        schema_rejected_rules(schema),
    ) + _vocabulary_errors(
        "expectError",
        prose_expect_errors(case_format_markdown),
        schema_expect_errors(schema),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.case_format_vocab_check <spec-dir>",
            file=sys.stderr,
        )
        return 2
    spec_dir = Path(argv[0])
    case_format_path = spec_dir / "m-case-format.md"
    if not case_format_path.is_file():
        print(f"not a file: {case_format_path}", file=sys.stderr)
        return 2

    case_format_markdown = case_format_path.read_text(encoding="utf-8")
    schema = load_json(schemas_dir(spec_dir) / "compatibility-case.schema.json")

    try:
        errors = check(case_format_markdown, schema)
    except VocabMismatch as exc:
        print(f"case-format vocabulary check FAILED: {exc}", file=sys.stderr)
        return 1

    if errors:
        print(
            f"case-format vocabulary check FAILED ({len(errors)} mismatch(es)):",
            file=sys.stderr,
        )
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        "case-format vocabulary check OK: prose and schema rejectedRule and "
        "expectError vocabularies match"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
