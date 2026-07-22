"""Machine gate for the m-descriptor ingestion and export contract::

    uv run python -m reference_harness.descriptor_contract_check core/compatibility

Two contract facts are asserted, both Docker-free:

1. **Ingestion fixtures** — every canonical invalid-descriptor fixture under
   ``core/compatibility/descriptor-errors/`` fails in its expected phase. A
   fixture is a raw document (``<stem>.json`` / ``<stem>.yaml``, byte-exact and
   deliberately outside ``models/``) paired by stem with an expectation sidecar
   (``<stem>.expected.yaml``) carrying the expected phase and code and, for the
   schema and value phases, the expected canonically ordered violation list.
   This module
   implements the m-descriptor canonical violation ordering once — equality and
   order are ``(path, rule)`` with ``message`` excluded, a strict path prefix
   first, member names by codepoint, array indices numeric, branching keywords
   (``oneOf`` / ``anyOf`` / ``not``) collapsed to one violation at the branching
   path, and equal ``(path, rule)`` violations collapsed to one. The value
   phase judges only schema-valid documents and realizes the m-descriptor
   named rejections ("Type spellings"): a ``type-spelling-invalid`` violation
   for a decimal spelling whose parameters break the m-core bounds or carry
   non-canonical digits.
2. **Export determinism** — every corpus model under ``models/`` canonicalizes
   to a byte-identical fixed point in both JSON and YAML (serialize ->
   deserialize -> serialize), the m-descriptor byte-deterministic export law
   the round-trip gates rely on.

A malformed fixture set — an unpaired document or sidecar, a stem with two
documents, an unparseable or mis-shaped expectation, or an empty fixture
directory — is itself a loud failure, never a vacuous pass.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

from . import serde
from .paths import schemas_dir
from .schemas import load_json

__all__ = [
    "Violation",
    "canonical_value_violations",
    "canonical_violations",
    "export_determinism_errors",
    "fixture_errors",
    "main",
    "violation_sort_key",
]


@dataclass(frozen=True)
class Violation:
    """One ``DescriptorSchemaViolation`` identity: document path plus failing
    JSON-Schema keyword. The explanatory message is excluded from equality and
    ordering by the m-descriptor contract, so it is not a member."""

    path: tuple[str | int, ...]
    rule: str


def violation_sort_key(violation: Violation) -> tuple[tuple[tuple[int, int, str], ...], str]:
    """The m-descriptor canonical violation ordering, ``(path, rule)``.

    A strict path prefix orders before its extensions (tuple comparison over
    per-segment keys); at the first differing segment, array indices compare
    numerically and member names by codepoint. Within one document the two
    differing segments address the same node and are therefore the same kind;
    the cross-kind key order is a total-order backstop, never observable there.
    Equal paths order by ``rule`` codepoint.
    """
    path_key = tuple(
        (0, segment, "") if isinstance(segment, int) else (1, 0, segment)
        for segment in violation.path
    )
    return (path_key, violation.rule)


def canonical_violations(document: Any, schema: dict[str, Any]) -> list[Violation]:
    """The document's schema violations, deduplicated and canonically ordered.

    Top-level validator errors already realize the branching-collapse rule: a
    failed ``oneOf`` / ``anyOf`` / ``not`` surfaces as one error at the
    branching location (its per-branch sub-errors stay in the validator's
    context and are deliberately not descended), while ``allOf``, ``if`` /
    ``then``, ``properties``, ``items``, ``prefixItems``, and ``$ref`` are
    transparent. An empty result means the document is schema-valid.

    The *schema* is a trusted precondition, not a judged input: a schema the
    Draft 2020-12 meta-schema rejects can raise arbitrary validator errors,
    and one whose references do not resolve raises
    ``referencing.exceptions.Unresolvable``. The CLI boundary vets the schema
    and converts both into reported diagnostics.
    """
    validator = Draft202012Validator(schema)
    identities = {
        Violation(tuple(error.absolute_path), str(error.validator))
        for error in validator.iter_errors(document)
    }
    return sorted(identities, key=violation_sort_key)


_DECIMAL_SPELLING = re.compile(r"^decimal\(([0-9]+),([0-9]+)\)$")
_CANONICAL_DIGITS = re.compile(r"^(?:0|[1-9][0-9]*)$")


def _decimal_spelling_invalid(spelling: str) -> bool:
    """True when a schema-valid decimal ``type`` spelling denotes an
    unconstructible core value: a parameter with non-canonical digits (a
    superfluous leading zero), a zero precision, or a scale exceeding the
    precision. A non-decimal spelling is never judged here — the schema owns
    its validity."""
    match = _DECIMAL_SPELLING.match(spelling)
    if match is None:
        return False
    precision_text, scale_text = match.groups()
    if not (_CANONICAL_DIGITS.match(precision_text) and _CANONICAL_DIGITS.match(scale_text)):
        return True
    precision, scale = int(precision_text), int(scale_text)
    return precision < 1 or scale > precision


def canonical_value_violations(document: Any) -> list[Violation]:
    """The document's value-phase violations (m-descriptor "Phase 3 — value"),
    deduplicated and canonically ordered.

    Meaningful only for a schema-valid document. The named rejection set is
    exactly the m-descriptor "Type spellings" rules: every ``type`` member
    holding a decimal spelling whose parameters break the m-core bounds or
    carry non-canonical digits is one ``type-spelling-invalid`` violation at
    that member's document path. An empty result means the document is
    value-valid."""
    identities: set[Violation] = set()

    def walk(node: Any, path: tuple[str | int, ...]) -> None:
        if isinstance(node, dict):
            spelling = node.get("type")
            if isinstance(spelling, str) and _decimal_spelling_invalid(spelling):
                identities.add(Violation((*path, "type"), "type-spelling-invalid"))
            for key, child in node.items():
                walk(child, (*path, key))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, (*path, index))

    walk(document, ())
    return sorted(identities, key=violation_sort_key)


# --- the ingestion fixture gate ----------------------------------------------

_DOCUMENT_FORMATS = {".json": serde.JSON, ".yaml": serde.YAML}
_EXPECTED_SUFFIX = ".expected.yaml"
_PHASE_CODES = {
    "syntax": "descriptor-invalid-syntax",
    "schema": "descriptor-schema-invalid",
    "value": "descriptor-value-invalid",
}


def _format_path(path: tuple[str | int, ...]) -> str:
    return "/".join(str(segment) for segment in path) or "<root>"


def _format_violations(violations: list[Violation]) -> str:
    return ", ".join(f"({_format_path(v.path)}, {v.rule})" for v in violations)


def _decode(text: str, fmt: str) -> tuple[bool, object]:
    """``(True, document)`` when *text* parses in *fmt*; ``(False, None)`` on a
    phase-1 syntax failure. The parser is keyed by the fixture's format — a
    YAML parser accepts JSON-ish text a JSON parser rejects, so a ``.json``
    fixture must be judged by a JSON parser."""
    try:
        if fmt == serde.JSON:
            return True, json.loads(text)
        return True, yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError):
        return False, None


def _expected_violations(raw: object, label: str, errors: list[str]) -> list[Violation] | None:
    """Parse a sidecar's ``violations`` list into identities; ``None`` (with
    errors appended) when its shape is invalid."""
    if not isinstance(raw, list) or not raw:
        errors.append(f"{label}: `violations` must be a nonempty list")
        return None
    parsed: list[Violation] = []
    for position, entry in enumerate(raw):
        entry_label = f"{label}: violations[{position}]"
        if not isinstance(entry, dict) or set(entry) != {"path", "rule"}:
            errors.append(f"{entry_label} must carry exactly `path` and `rule`")
            return None
        path, rule = entry["path"], entry["rule"]
        segments_valid = isinstance(path, list) and all(
            isinstance(segment, str | int) and not isinstance(segment, bool) for segment in path
        )
        if not segments_valid:
            errors.append(f"{entry_label} path must be a list of member names and array indices")
            return None
        if not isinstance(rule, str) or not rule:
            errors.append(f"{entry_label} rule must be a nonempty rule name")
            return None
        parsed.append(Violation(tuple(path), rule))
    return parsed


def _load_expectation(expected_path: Path, errors: list[str]) -> tuple[str, list[Violation]] | None:
    """``(phase, expected_violations)`` from a sidecar — the list is empty for
    the syntax phase, which expects no violations; ``None`` (with errors
    appended) when the sidecar is unreadable or mis-shaped."""
    label = expected_path.name
    try:
        raw = yaml.safe_load(expected_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"{label}: unreadable expectation sidecar: {exc}")
        return None
    if not isinstance(raw, dict):
        errors.append(f"{label}: the expectation sidecar must be a mapping")
        return None
    phase = raw.get("phase")
    if phase not in _PHASE_CODES:
        errors.append(f"{label}: `phase` must be one of {sorted(_PHASE_CODES)}, got {phase!r}")
        return None
    if raw.get("code") != _PHASE_CODES[phase]:
        errors.append(
            f"{label}: phase {phase!r} requires `code: {_PHASE_CODES[phase]}`, "
            f"got {raw.get('code')!r}"
        )
        return None
    expected_keys = {"phase", "code"} | ({"violations"} if phase in ("schema", "value") else set())
    if set(raw) != expected_keys:
        errors.append(f"{label}: expectation keys must be exactly {sorted(expected_keys)}")
        return None
    if phase == "syntax":
        return phase, []
    violations = _expected_violations(raw["violations"], label, errors)
    if violations is None:
        return None
    return phase, violations


def _fixture_pair_errors(
    document_path: Path, expected_path: Path, schema: dict[str, Any]
) -> list[str]:
    """Run one document/sidecar pair through the ingestion phases and compare
    the outcome with the sidecar's expectation. A violation-carrying phase
    (schema / value) additionally asserts every earlier phase passes — no
    phase reports another phase's failures."""
    errors: list[str] = []
    expectation = _load_expectation(expected_path, errors)
    if expectation is None:
        return errors
    phase, expected = expectation
    label = document_path.name
    fmt = _DOCUMENT_FORMATS[document_path.suffix]
    try:
        text = document_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{label}: unreadable fixture document: {exc}"]
    parsed, document = _decode(text, fmt)

    if phase == "syntax":
        if parsed:
            errors.append(
                f"{label}: expected a phase-1 syntax failure but the {fmt} text parses cleanly"
            )
        return errors

    if not parsed:
        errors.append(
            f"{label}: expected phase-{'2 schema' if phase == 'schema' else '3 value'} "
            f"violations but the {fmt} text does not parse"
        )
        return errors
    schema_violations = canonical_violations(document, schema)
    if phase == "schema":
        actual = schema_violations
        if not actual:
            errors.append(f"{label}: expected schema violations but the document is schema-valid")
            return errors
    else:
        if schema_violations:
            errors.append(
                f"{label}: expected phase-3 value violations but the document is "
                f"schema-invalid: [{_format_violations(schema_violations)}]"
            )
            return errors
        actual = canonical_value_violations(document)
        if not actual:
            errors.append(f"{label}: expected value violations but the document is value-valid")
            return errors
    canonical_expected = sorted(set(expected), key=violation_sort_key)
    if set(expected) != set(actual):
        errors.append(
            f"{label}: expected violations differ from the canonical violations: "
            f"expected [{_format_violations(canonical_expected)}], "
            f"actual [{_format_violations(actual)}]"
        )
    if expected != canonical_expected:
        errors.append(
            f"{label}: expected violations are not in canonical order (or repeat an "
            f"identity): canonical order is [{_format_violations(canonical_expected)}]"
        )
    return errors


def fixture_errors(fixture_dir: Path, schema: dict[str, Any]) -> list[str]:
    """Every ingestion-contract inconsistency in the fixture set (empty ⇒ the
    real fixtures behave exactly as their sidecars expect).

    Pairing is by stem: each ``<stem>.json`` / ``<stem>.yaml`` document needs
    exactly one ``<stem>.expected.yaml`` sidecar and vice versa; any other
    file, an ambiguous stem, or an entirely empty directory is reported.
    """
    errors: list[str] = []
    documents: dict[str, Path] = {}
    expectations: dict[str, Path] = {}
    for path in sorted(fixture_dir.iterdir()):
        name = path.name
        if not path.is_file():
            errors.append(f"unexpected non-file entry in the fixture set: {name}")
        elif name.endswith(_EXPECTED_SUFFIX):
            expectations[name[: -len(_EXPECTED_SUFFIX)]] = path
        elif path.suffix in _DOCUMENT_FORMATS:
            stem = name[: -len(path.suffix)]
            if stem in documents:
                errors.append(
                    f"fixture stem {stem!r} has two documents "
                    f"({documents[stem].name} and {name}); one raw document per stem"
                )
            else:
                documents[stem] = path
        else:
            errors.append(
                f"unexpected file {name}: fixtures are <stem>.json or <stem>.yaml "
                f"plus <stem>{_EXPECTED_SUFFIX}"
            )
    for stem in sorted(set(documents) - set(expectations)):
        errors.append(f"document {documents[stem].name} has no {stem}{_EXPECTED_SUFFIX} sidecar")
    for stem in sorted(set(expectations) - set(documents)):
        errors.append(
            f"expectation {expectations[stem].name} has no {stem}.json or {stem}.yaml document"
        )
    if not documents and not errors:
        errors.append(f"no descriptor-error fixtures found under {fixture_dir}")
    for stem in sorted(set(documents) & set(expectations)):
        errors.extend(_fixture_pair_errors(documents[stem], expectations[stem], schema))
    return errors


# --- the export-determinism gate ---------------------------------------------


def export_determinism_errors(models_dir: Path) -> list[str]:
    """Every corpus model that breaks the byte-deterministic export law
    (empty ⇒ all models canonicalize to a byte-identical fixed point).

    For each model and each format: ``serialize(canonical(model))`` must be
    byte-identical after one more deserialize/serialize cycle, and the cycled
    value must equal the original. A model the canonical writer cannot
    serialize at all is reported rather than raised.
    """
    errors: list[str] = []
    model_paths = sorted(models_dir.glob("**/*.y*ml"))
    if not model_paths:
        return [f"no corpus models found under {models_dir}"]
    for path in model_paths:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            errors.append(f"model {path.name}: unreadable: {exc}")
            continue
        for fmt in serde.FORMATS:
            try:
                first = serde.serialize(document, fmt)
                parsed = serde.deserialize(first, fmt)
                second = serde.serialize(parsed, fmt)
            except (TypeError, ValueError, yaml.YAMLError) as exc:
                errors.append(f"model {path.name}: canonical {fmt} export failed: {exc}")
                continue
            if first != second:
                errors.append(
                    f"model {path.name}: canonical {fmt} export is not byte-deterministic"
                )
            elif serde.canonical(parsed) != serde.canonical(document):
                errors.append(f"model {path.name}: canonical {fmt} round-trip changed the document")
    return errors


def main(argv: list[str]) -> int:
    """CLI entry point: run both gates over the compatibility tree *argv[0]*
    (the schema location is derived via `schemas_dir`).

    Exit codes: 0 — every fixture matches its expectation and every model
    export is deterministic; 1 — a contract inconsistency, a malformed fixture
    set, or a malformed metamodel schema (unparseable JSON, a non-object root,
    a document the Draft 2020-12 meta-schema rejects, or an unresolvable
    schema reference); 2 — usage error, or a required directory or the schema
    file is missing or unreadable.
    """
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.descriptor_contract_check <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(argv[0])
    fixture_dir = compatibility_root / "descriptor-errors"
    models_dir = compatibility_root / "models"
    for required in (compatibility_root, fixture_dir, models_dir):
        if not required.is_dir():
            print(f"not a directory: {required}", file=sys.stderr)
            return 2

    try:
        schema_path = schemas_dir(compatibility_root) / "metamodel.schema.json"
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
    if not isinstance(schema, dict):
        print(
            f"malformed schema JSON in {schema_path}: the document root is not a JSON object",
            file=sys.stderr,
        )
        return 1
    # ``check_schema`` rejects every defect the Draft 2020-12 meta-schema can
    # see, including ``pattern`` regex validity via its format checks. Reference
    # resolution is lazy, so a dangling ``$ref`` in a meta-schema-valid schema
    # surfaces only when fixture validation reaches it; the guard below converts
    # that residual escape into the same diagnostic.
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        print(
            f"malformed Draft 2020-12 schema in {schema_path}: {exc.json_path}: {exc.message}",
            file=sys.stderr,
        )
        return 1

    try:
        errors = fixture_errors(fixture_dir, schema)
    except Unresolvable as exc:
        print(
            f"malformed Draft 2020-12 schema in {schema_path}: "
            f"unresolvable schema reference {exc.ref!r}",
            file=sys.stderr,
        )
        return 1
    errors += export_determinism_errors(models_dir)
    if errors:
        print(f"descriptor contract check FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(
        "descriptor contract check OK: every descriptor-error fixture fails in its expected "
        "phase and every corpus model export is byte-deterministic"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
