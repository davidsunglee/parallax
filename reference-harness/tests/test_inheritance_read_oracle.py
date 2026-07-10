"""DB-free unit tests for the abstract-target inheritance READ oracle (Phase 4).

The read-side counterpart of the write-derivation oracle (m-inheritance / m-sql,
resolved Q6): from the descriptor alone the harness derives a narrow's effective
concrete-subtype set and its validity, the abstract-read projection superset, and
the per-row `familyVariant` (`tagValue` -> concrete subtype name). These tests
exercise that derivation with no database:

* the narrow four-step validation ACCEPTS a valid / redundant narrow and RAISES the
  exact operation rule for a broadening narrow, an empty effective set, and a
  concrete-subtype attribute used outside a compatible narrowing scope;
* the family-variant map and the concrete superset are derived from the ancestry;
* `_materialize_family_variant` replaces the raw tag column with the derived
  `familyVariant`, and FAILS loudly when the golden projection omits a superset
  column or the tag column.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, load_model
from reference_harness.case_runner import CaseFailure, _materialize_family_variant
from reference_harness.inheritance import (
    NARROW_EMPTY_EFFECTIVE_SET,
    NARROW_OUTSIDE_POSITION,
    SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE,
    Family,
    concrete_superset_columns,
    tag_value_to_subtype,
    validate_operation_inheritance,
)
from reference_harness.value_object_resolve import RejectionError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


def _animal_defs() -> list[dict[str, Any]]:
    return load_model(_COMPATIBILITY_ROOT, "models/animal.yaml").entity_defs


# --- effective concrete-set derivation --------------------------------------


def test_effective_and_narrow_resolution() -> None:
    family = Family(_animal_defs())
    assert family.effective_concrete_set("Animal") == ["Dog", "Cat", "WildBoar"]
    assert family.effective_concrete_set("Pet") == ["Dog", "Cat"]
    assert family.effective_concrete_set("Dog") == ["Dog"]
    # An abstract subtype and its explicit concrete list resolve to the same SET.
    assert set(family.resolve_to_set(["Pet"])) == {"Dog", "Cat"}
    assert set(family.resolve_to_set(["Cat", "Dog"])) == {"Dog", "Cat"}


# --- the narrow four-step validation ----------------------------------------


def test_valid_and_redundant_narrows_are_accepted() -> None:
    defs = _animal_defs()
    # Narrow the root to a proper subset (Pet -> Dog, Cat).
    validate_operation_inheritance(
        defs,
        {"narrow": {"entity": "Animal", "to": ["Pet"], "operand": {"all": {}}}},
        position="Animal",
    )
    # Redundant narrow (a position to itself) is a no-op, not a rejection.
    validate_operation_inheritance(
        defs,
        {"narrow": {"entity": "Pet", "to": ["Pet"], "operand": {"all": {}}}},
        position="Pet",
    )
    # A concrete-subtype attribute IS in scope once narrowed to that subtype.
    validate_operation_inheritance(
        defs,
        {
            "narrow": {
                "entity": "Animal",
                "to": ["Dog"],
                "operand": {"greaterThan": {"attr": "Dog.barkVolume", "value": 3}},
            }
        },
        position="Animal",
    )


def test_broadening_narrow_is_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation_inheritance(
            _animal_defs(),
            {"narrow": {"entity": "Pet", "to": ["WildBoar"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_narrow_broadening_beyond_the_threaded_position_is_rejected() -> None:
    # A top-level narrow whose `entity` names a position (Animal, {Dog, Cat, WildBoar})
    # BROADER than the active threaded position (Pet, {Dog, Cat}) must not be able to
    # reach a subtype outside the active position: narrowing to [WildBoar] resolves
    # OUTSIDE Pet, so it is rejected. The subset check binds to the active position
    # (the read's targetEntity), not to `effective_concrete_set(entity)`. This needs an
    # explicit `position="Pet"`, so it lives here as a unit test, not the corpus (a
    # `rejected` case carries no `targetEntity`).
    with pytest.raises(RejectionError) as exc:
        validate_operation_inheritance(
            _animal_defs(),
            {"narrow": {"entity": "Animal", "to": ["WildBoar"], "operand": {"all": {}}}},
            position="Pet",
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_nested_narrow_cannot_broaden_back_out() -> None:
    # After the OUTER narrow (Pet -> [Dog]) the active position is {Dog}. The INNER
    # narrow declares the broader `entity` Animal and narrows to [Cat] — broadening back
    # out of {Dog}. Even though [Cat] is inside Animal's own set, it is outside the
    # threaded active position, so it is rejected. (The corpus witness is
    # m-inheritance-042, which needs no targetEntity; this pins the same via the walker.)
    with pytest.raises(RejectionError) as exc:
        validate_operation_inheritance(
            _animal_defs(),
            {
                "narrow": {
                    "entity": "Pet",
                    "to": ["Dog"],
                    "operand": {
                        "narrow": {"entity": "Animal", "to": ["Cat"], "operand": {"all": {}}}
                    },
                }
            },
        )
    assert exc.value.rule == NARROW_OUTSIDE_POSITION


def test_narrow_whose_entity_is_broader_than_position_but_to_is_within_is_accepted() -> None:
    # Boundary lock (no false rejection): a narrow whose `entity` (Animal) is BROADER
    # than the active position (Pet) is NOT rejected for the mismatch alone — the entity
    # position is clamped to the active position. As long as `to` ([Dog]) lands inside
    # the active position (Pet = {Dog, Cat}), the narrow is valid. This is the twin of
    # the rejection above: identical entity/position, a `to` that stays in scope.
    validate_operation_inheritance(
        _animal_defs(),
        {"narrow": {"entity": "Animal", "to": ["Dog"], "operand": {"all": {}}}},
        position="Pet",
    )


def test_narrow_to_empty_effective_set_is_rejected() -> None:
    # An abstract subtype with NO concrete descendants resolves to the empty set;
    # narrowing to it is rejected as an empty effective set. Built inline so the
    # corpus families (every abstract subtype has concretes) stay untouched.
    defs = [
        {
            "name": "Root",
            "inheritance": {"role": "root", "strategy": "table-per-hierarchy", "tag": {"column": "kind"}},
            "attributes": [{"name": "id", "type": "int64", "column": "id", "primaryKey": True}],
        },
        {
            "name": "Empty",
            "inheritance": {"role": "abstract-subtype", "parent": "Root"},
            "attributes": [],
        },
        {
            "name": "Real",
            "table": "root",
            "inheritance": {"role": "concrete-subtype", "parent": "Root", "tagValue": "real"},
            "attributes": [{"name": "v", "type": "int32", "column": "v", "nullable": True}],
        },
    ]
    with pytest.raises(RejectionError) as exc:
        validate_operation_inheritance(
            defs,
            {"narrow": {"entity": "Root", "to": ["Empty"], "operand": {"all": {}}}},
        )
    assert exc.value.rule == NARROW_EMPTY_EFFECTIVE_SET


def test_subtype_attribute_outside_narrow_scope_is_rejected() -> None:
    with pytest.raises(RejectionError) as exc:
        validate_operation_inheritance(
            _animal_defs(),
            {"greaterThan": {"attr": "Dog.barkVolume", "value": 5}},
        )
    assert exc.value.rule == SUBTYPE_ATTRIBUTE_OUTSIDE_NARROW_SCOPE


def test_inherited_attribute_is_always_in_scope() -> None:
    # `name` is declared on the root Animal, so it is available to every concrete in
    # any position — a root-position predicate on it is NOT a subtype-scope violation.
    validate_operation_inheritance(
        _animal_defs(), {"eq": {"attr": "Animal.name", "value": "Rex"}}, position="Animal"
    )


def test_non_inheritance_model_is_a_noop() -> None:
    defs = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml").entity_defs
    validate_operation_inheritance(defs, {"eq": {"attr": "Customer.name", "value": "Ada"}})


# --- familyVariant + projection superset derivation -------------------------


def test_tag_value_to_subtype_map() -> None:
    assert tag_value_to_subtype(_animal_defs()) == {
        "dog": "Dog",
        "cat": "Cat",
        "boar": "WildBoar",
    }


def test_concrete_superset_columns() -> None:
    defs = _animal_defs()
    # Pet's descendants only — no tusk_length; the tag column is included.
    pet = set(concrete_superset_columns(defs, ["Dog", "Cat"]))
    assert pet == {"id", "kind", "name", "license_id", "bark_volume", "indoor"}
    whole = set(concrete_superset_columns(defs, ["Dog", "Cat", "WildBoar"]))
    assert whole == pet | {"tusk_length"}


# --- _materialize_family_variant --------------------------------------------


# The full Animal-family concrete superset projected with the raw tag column
# (`kind`) — the shape an abstract-root read of Animal MUST emit. The failing-mode
# tests drop one column from this to witness the row-count-independent check.
_ANIMAL_GOLDEN = (
    "select t0.id, t0.name, t0.license_id, t0.bark_volume, "
    "t0.indoor, t0.tusk_length, t0.kind from animal t0"
)


def _read_case(target: str, operation: dict[str, Any], golden: str = _ANIMAL_GOLDEN) -> Case:
    model = load_model(_COMPATIBILITY_ROOT, "models/animal.yaml")
    raw = {
        "model": "models/animal.yaml",
        "tags": ["m-inheritance"],
        "shape": "read",
        "when": {"targetEntity": target, "operation": operation},
        "then": {"statements": [{"sql": {"postgres": golden}}], "rows": []},
    }
    return Case(path=Path("m-inheritance-999-x.yaml"), raw=raw, model=model)


def _dog_row() -> dict[str, Any]:
    return {
        "id": 1,
        "name": "Rex",
        "license_id": "L-100",
        "bark_volume": 7,
        "indoor": None,
        "tusk_length": None,
        "kind": "dog",
    }


def test_materialize_replaces_tag_with_family_variant() -> None:
    case = _read_case("Animal", {"all": {}})
    out = _materialize_family_variant(case, [_dog_row()])
    assert out == [
        {
            "id": 1,
            "name": "Rex",
            "license_id": "L-100",
            "bark_volume": 7,
            "indoor": None,
            "tusk_length": None,
            "familyVariant": "Dog",
        }
    ]


def test_materialize_is_noop_for_concrete_target() -> None:
    case = _read_case("Dog", {"all": {}})
    rows = [{"id": 1, "name": "Rex", "license_id": "L-100", "bark_volume": 7}]
    assert _materialize_family_variant(case, rows) == rows


def test_materialize_fails_when_superset_column_missing() -> None:
    # The GOLDEN drops WildBoar's tusk_length, so the Animal superset is not projected.
    # The check reads the projection from the golden SQL, not the sampled row.
    golden = (
        "select t0.id, t0.name, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.kind from animal t0"
    )
    case = _read_case("Animal", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="concrete-superset column"):
        _materialize_family_variant(case, [_dog_row()])


def test_materialize_fails_when_tag_column_missing() -> None:
    # Pet's superset (no tusk_length) but with the tag column `kind` dropped from the GOLDEN.
    golden = "select t0.id, t0.name, t0.license_id, t0.bark_volume, t0.indoor from animal t0"
    case = _read_case("Pet", {"all": {}}, golden=golden)
    row = {"id": 1, "name": "Rex", "license_id": "L-100", "bark_volume": 7, "indoor": None}
    with pytest.raises(CaseFailure, match="tag column"):
        _materialize_family_variant(case, [row])


# --- row-count-independence of the projection-shape check (Phase 4 review) ------
#
# The projection shape is derived from the GOLDEN SELECT, not a sample row, so a
# ZERO-row abstract-target read still witnesses a golden that drops a superset / tag
# column. Before this fix the check was gated `if rows:` and read `rows[0].keys()`, so
# these empty-result cases passed silently (nothing to inspect). They are the
# reproduce-then-green witnesses for closing that gap.


def test_materialize_zero_row_missing_superset_column_still_fails() -> None:
    golden = (
        "select t0.id, t0.name, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.kind from animal t0"  # WildBoar's tusk_length dropped
    )
    case = _read_case("Animal", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="concrete-superset column"):
        _materialize_family_variant(case, [])


def test_materialize_zero_row_missing_tag_column_still_fails() -> None:
    golden = (
        "select t0.id, t0.name, t0.license_id, t0.bark_volume, "
        "t0.indoor, t0.tusk_length from animal t0"  # tag column `kind` dropped
    )
    case = _read_case("Animal", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="tag column"):
        _materialize_family_variant(case, [])


def test_materialize_zero_row_correct_golden_passes() -> None:
    # Positive twin: an empty result over a correct full-superset + tag golden
    # materializes nothing and does NOT raise.
    case = _read_case("Animal", {"all": {}})
    assert _materialize_family_variant(case, []) == []
