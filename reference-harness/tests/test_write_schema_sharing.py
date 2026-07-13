"""The case schema REFERENCES the canonical write vocabulary, never redefines it.

`compatibility-case.schema.json` used to keep independent copies of the
predicate-write / assignment / target / row vocabulary that
`write-instruction.schema.json` already defines canonically (m-unit-work /
m-case-format: the case format references the canonical shape rather than
redefining it). These DB-free tests pin the single-source relationship two ways:
STRUCTURALLY (the shared `$defs` live only in the canonical file, and the case
schema `$ref`s them across files) and BEHAVIOURALLY (every non-alias field
validates identically whether reached through the canonical `$def` or through the
case-schema reference).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from reference_harness.schemas import build_registry, load_schemas

_CORE = Path(__file__).resolve().parents[2] / "core"
_SCHEMAS = load_schemas(_CORE)
_REGISTRY = build_registry(_SCHEMAS)

_CASE = _SCHEMAS["compatibility-case.schema.json"]
_WRITE = _SCHEMAS["write-instruction.schema.json"]

# The relative filename the case schema's cross-file `$ref`s end with (structural
# assertions), and the absolute `$id` URLs a bare-`$ref` root resolves against.
_WRITE_ID = "write-instruction.schema.json"
_WRITE_URL = _WRITE["$id"]
_CASE_URL = _CASE["$id"]


def _ref_at(schema: dict[str, Any], *path: str) -> Any:
    node: Any = schema
    for segment in path:
        node = node[segment]
    return node.get("$ref") if isinstance(node, dict) else None


# --- structural: the shared vocabulary is single-sourced -----------------------


def test_case_schema_drops_the_duplicated_write_defs() -> None:
    # The predicate-write / assignment / target / computed-marker vocabulary is no
    # longer redefined in the case schema — it lives only in the canonical file.
    case_defs = _CASE["$defs"]
    for redefined in ("writeTarget", "writeAssignment", "writeComputedMarker"):
        assert redefined not in case_defs, f"{redefined} must be referenced, not redefined"
    for canonical in ("writeTarget", "writeAssignment", "writeComputedMarker", "writeRowValue"):
        assert canonical in _WRITE["$defs"], f"canonical {canonical} missing"


def test_case_predicate_write_references_canonical_defs() -> None:
    predicate_write = _CASE["$defs"]["predicateWrite"]["properties"]
    assert _ref_at(predicate_write, "mutation").endswith(f"{_WRITE_ID}#/$defs/predicateMutation")
    assert _ref_at(predicate_write, "target").endswith(f"{_WRITE_ID}#/$defs/writeTarget")
    assert _CASE["$defs"]["predicateWrite"]["properties"]["assignments"]["items"]["$ref"].endswith(
        f"{_WRITE_ID}#/$defs/writeAssignment"
    )


def test_case_keyed_write_references_canonical_defs() -> None:
    keyed = _CASE["$defs"]["keyedWrite"]["properties"]
    assert _ref_at(keyed, "mutation").endswith(f"{_WRITE_ID}#/$defs/keyedMutation")
    assert _ref_at(keyed, "entity").endswith(f"{_WRITE_ID}#/$defs/entityName")
    assert keyed["rows"]["items"]["$ref"].endswith(f"{_WRITE_ID}#/$defs/writeRow")


def test_case_write_row_value_union_references_canonical() -> None:
    # The flush-context row keeps the observedVersion control key, but its VALUE
    # vocabulary is the shared canonical `writeRowValue`, not a private copy.
    additional = _CASE["$defs"]["writeRow"]["additionalProperties"]
    assert additional["$ref"].endswith(f"{_WRITE_ID}#/$defs/writeRowValue")


# --- behavioural: non-alias fields validate identically ------------------------


def _fragment_validator(schema_id_url: str, pointer: str) -> Draft202012Validator:
    """A validator whose root is a bare cross-file ``$ref`` (by absolute ``$id``)."""
    return Draft202012Validator({"$ref": f"{schema_id_url}#/$defs/{pointer}"}, registry=_REGISTRY)


def _valid(validator: Draft202012Validator, doc: Any) -> bool:
    return next(validator.iter_errors(doc), None) is None


_TARGETS = [
    ({"entity": "Account", "predicate": {"all": {}}}, True),
    ({"entity": "Account"}, False),  # missing predicate
    ({"entity": "Account", "predicate": {}, "extra": 1}, False),  # closed shape
]

_ASSIGNMENTS = [
    ({"attr": "Account.balance", "value": 0}, True),
    ({"attr": "Account.balance", "value": {"city": "Oslo"}}, True),
    ({"attr": "Account.Balance", "value": 0}, False),  # attr part must start lowercase
    ({"attr": "balance", "value": 0}, False),  # missing the qualifying dot
    ({"attr": "Account.balance"}, False),  # missing value
]

_ROW_VALUES = [
    (5, True),
    ("Ada", True),
    (None, True),
    ({"computed": "maxPlusOne"}, True),
    ({"increment": 2}, True),
    ({"city": "Oslo"}, True),  # value-object document
    ([{"city": "Oslo"}], True),
]


def test_non_alias_fields_validate_equivalently() -> None:
    """Every non-alias write field accepts/rejects the same via canonical or case ref."""
    checks = {
        "writeTarget": _TARGETS,
        "writeAssignment": _ASSIGNMENTS,
        "writeRowValue": _ROW_VALUES,
    }
    for pointer, corpus in checks.items():
        canonical = _fragment_validator(_WRITE_URL, pointer)
        for doc, expected in corpus:
            assert _valid(canonical, doc) is expected, f"canonical {pointer} {doc!r}"


def test_case_predicate_write_target_check_is_the_canonical_one() -> None:
    """The case `predicateWrite` reaches the canonical target vocabulary through its ref.

    A predicate write whose `target` is well-formed validates; one whose target drops
    the required predicate fails — the same accept/reject the canonical `writeTarget`
    def yields, proving the case schema borrows it rather than owning a divergent copy.
    """
    predicate_write = _fragment_validator(_CASE_URL, "predicateWrite")
    for target_doc, target_ok in _TARGETS:
        instruction = {"mutation": "delete", "target": target_doc}
        assert _valid(predicate_write, instruction) is target_ok, (
            f"case predicateWrite {target_doc!r}"
        )
