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
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
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
        "select t0.id, t0.name, t0.license_id, t0.bark_volume, t0.indoor, t0.kind from animal t0"
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


# --- table-per-concrete-subtype `union all` oracle (Phase 5) -----------------
#
# The TPCS counterpart of the TPH projection-shape check: from the descriptor alone
# the harness recomputes the `union all` branch count/order (the effective concrete
# set in descriptor order), the stable superset projection every branch shares, and
# each branch's `familyVariant` subtype-name LITERAL (the settled TPCS asymmetry —
# TPCS projects the variant literal per branch, TPH derives it from the raw tag).


def _document_model() -> Any:
    return load_model(_COMPATIBILITY_ROOT, "models/document.yaml")


def _document_defs() -> list[dict[str, Any]]:
    return _document_model().entity_defs


# The canonical three-branch abstract-root golden (Document over Invoice / Receipt /
# Memo). The failing-mode tests mutate one aspect of this to witness the check.
_DOCUMENT_ROOT_UNION = (
    "select t0.id, t0.title, t0.currency, t0.amount_due, "
    "cast(null as decimal(18, 2)) paid_amount, cast(null as varchar(64)) body, "
    "'Invoice' family_variant from invoice t0 "
    "union all "
    "select t0.id, t0.title, t0.currency, cast(null as decimal(18, 2)) amount_due, "
    "t0.paid_amount, cast(null as varchar(64)) body, 'Receipt' family_variant "
    "from receipt t0 "
    "union all "
    "select t0.id, t0.title, cast(null as varchar(3)) currency, "
    "cast(null as decimal(18, 2)) amount_due, cast(null as decimal(18, 2)) paid_amount, "
    "t0.body, 'Memo' family_variant from memo t0"
)


def _document_case(
    target: str, operation: dict[str, Any], golden: str = _DOCUMENT_ROOT_UNION
) -> Case:
    model = _document_model()
    raw = {
        "model": "models/document.yaml",
        "tags": ["m-inheritance"],
        "shape": "read",
        "when": {"targetEntity": target, "operation": operation},
        "then": {"statements": [{"sql": {"postgres": golden}}], "rows": []},
    }
    return Case(path=Path("m-inheritance-999-x.yaml"), raw=raw, model=model)


def test_document_effective_sets_and_descriptor_order() -> None:
    family = Family(_document_defs())
    assert family.concrete_descendants("Document") == ["Invoice", "Receipt", "Memo"]
    assert family.effective_concrete_set("FinancialDocument") == ["Invoice", "Receipt"]
    assert family.strategy_of("Document") == "table-per-concrete-subtype"


def test_tpcs_materialize_renames_family_variant_literal() -> None:
    # The DB projects the per-branch literal under `family_variant`; the oracle
    # renames it to `familyVariant` (no raw tag column exists to map).
    case = _document_case("Document", {"all": {}})
    invoice_row = {
        "id": 1,
        "title": "Invoice-A",
        "currency": "USD",
        "amount_due": 120,
        "paid_amount": None,
        "body": None,
        "family_variant": "Invoice",
    }
    (out,) = _materialize_family_variant(case, [invoice_row])
    assert "family_variant" not in out
    assert out["familyVariant"] == "Invoice"


def test_tpcs_zero_row_still_asserts_union_shape() -> None:
    # A correct golden over an empty result raises nothing but still runs the shape
    # assertion (row-count-independent, parsed from the golden text).
    case = _document_case("Document", {"all": {}})
    assert _materialize_family_variant(case, []) == []


def test_tpcs_wrong_branch_count_is_rejected() -> None:
    # Two branches for a three-concrete abstract root (Memo branch dropped).
    two_branch = " union all ".join(_DOCUMENT_ROOT_UNION.split(" union all ")[:2])
    case = _document_case("Document", {"all": {}}, golden=two_branch)
    with pytest.raises(CaseFailure, match="union all"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_branch_order_is_rejected() -> None:
    # Swap the Invoice and Receipt branches: branch order must be descriptor order.
    parts = _DOCUMENT_ROOT_UNION.split(" union all ")
    swapped = " union all ".join([parts[1], parts[0], parts[2]])
    case = _document_case("Document", {"all": {}}, golden=swapped)
    with pytest.raises(CaseFailure, match="descriptor-order"):
        _materialize_family_variant(case, [])


def test_tpcs_missing_superset_column_is_rejected() -> None:
    # Drop `body` from every branch's projection: the stable superset is incomplete.
    golden = _DOCUMENT_ROOT_UNION.replace(", cast(null as varchar(64)) body", "")
    golden = golden.replace(", t0.body", "")
    case = _document_case("Document", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="stable superset"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_variant_literal_is_rejected() -> None:
    # A branch whose familyVariant literal is not its concrete subtype name.
    golden = _DOCUMENT_ROOT_UNION.replace("'Memo' family_variant", "'Note' family_variant")
    case = _document_case("Document", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="familyVariant literal"):
        _materialize_family_variant(case, [])


def test_tpcs_concrete_target_is_a_noop() -> None:
    # A concrete-target TPCS read (Invoice) is an ordinary single-table read with no
    # familyVariant and no union — the oracle leaves it untouched.
    case = _document_case(
        "Invoice", {"all": {}}, golden="select t0.id, t0.amount_due from invoice t0"
    )
    rows = [{"id": 1, "amount_due": 120}]
    assert _materialize_family_variant(case, rows) == rows


def test_tpcs_narrow_to_multiple_concretes_shape() -> None:
    # A narrow to [Invoice, Memo] lowers to a two-branch union in descriptor order;
    # the oracle recomputes the shape from the narrow's effective set.
    golden = (
        "select t0.id, t0.title, t0.currency, t0.amount_due, "
        "cast(null as varchar(64)) body, 'Invoice' family_variant from invoice t0 "
        "union all "
        "select t0.id, t0.title, cast(null as varchar(3)) currency, "
        "cast(null as decimal(18, 2)) amount_due, t0.body, 'Memo' family_variant "
        "from memo t0"
    )
    case = _document_case(
        "Document",
        {"narrow": {"entity": "Document", "to": ["Invoice", "Memo"], "operand": {"all": {}}}},
        golden=golden,
    )
    memo_row = {
        "id": 1,
        "title": "Memo-A",
        "currency": None,
        "amount_due": None,
        "body": "Reminder",
        "family_variant": "Memo",
    }
    (out,) = _materialize_family_variant(case, [memo_row])
    assert out["familyVariant"] == "Memo"


# --- Phase 5 review remediations -------------------------------------------------
#
# Finding 1 (oracle side): the branch walk accepted any `SetOperation`, so a golden
# using a de-duplicating plain `union` (or `intersect`) passed the shape check.
# Finding 2: the shape check validated output NAMES and the trailing literal but not
# the per-column cast SHAPE, so a bare `null <col>` or a wrong-typed cast passed.
# Finding 3: the per-column cast type is asserted per dialect (Postgres `varchar` /
# MariaDB `char`). Finding 5: a real column colliding with the synthetic
# `family_variant` alias is rejected. All reproduce-then-green.


def test_tpcs_plain_union_is_rejected() -> None:
    # First arm is a de-duplicating `union`, not `union all` — the oracle must reject it.
    plain = _DOCUMENT_ROOT_UNION.replace(" union all ", " union ", 1)
    case = _document_case("Document", {"all": {}}, golden=plain)
    with pytest.raises(CaseFailure, match="union all"):
        _materialize_family_variant(case, [])


def test_tpcs_bare_null_placeholder_no_cast_is_rejected() -> None:
    # A non-applicable column projected as a bare `null` (no cast) gives the union an
    # untyped column; the placeholder MUST be `cast(null as <type>)`.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "cast(null as decimal(18, 2)) paid_amount", "null paid_amount"
    )
    case = _document_case("Document", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="cast"):
        _materialize_family_variant(case, [])


def test_tpcs_wrong_typed_placeholder_cast_is_rejected() -> None:
    # A non-applicable decimal column cast to a string type — same output name, wrong type.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "cast(null as decimal(18, 2)) paid_amount", "cast(null as varchar(9)) paid_amount"
    )
    case = _document_case("Document", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="declared type"):
        _materialize_family_variant(case, [])


def test_tpcs_applicable_column_projected_as_null_is_rejected() -> None:
    # Invoice's own `amount_due` projected as a NULL placeholder rather than the real
    # column reference — an applicable column MUST be a real reference.
    golden = _DOCUMENT_ROOT_UNION.replace(
        "t0.amount_due,", "cast(null as decimal(18, 2)) amount_due,", 1
    )
    case = _document_case("Document", {"all": {}}, golden=golden)
    with pytest.raises(CaseFailure, match="APPLICABLE"):
        _materialize_family_variant(case, [])


# The MariaDB abstract-root golden: bounded strings cast to `char`, decimals identical.
_DOCUMENT_ROOT_UNION_MARIADB = _DOCUMENT_ROOT_UNION.replace("varchar(64)", "char(64)").replace(
    "varchar(3)", "char(3)"
)


def test_tpcs_mariadb_char_cast_golden_is_accepted() -> None:
    case = _document_case("Document", {"all": {}})
    case.raw["then"]["statements"][0]["sql"]["mariadb"] = _DOCUMENT_ROOT_UNION_MARIADB
    assert _materialize_family_variant(case, []) == []


def test_tpcs_mariadb_varchar_cast_golden_is_rejected() -> None:
    # A MariaDB golden that used `varchar` (a Postgres-only CAST target) is rejected by
    # the per-dialect cast-type check — proving Finding 3's assertion is dialect-aware.
    bad_mariadb = _DOCUMENT_ROOT_UNION.replace("varchar(64)", "char(64)")  # leaves varchar(3)
    case = _document_case("Document", {"all": {}})
    case.raw["then"]["statements"][0]["sql"] = {"mariadb": bad_mariadb}
    with pytest.raises(CaseFailure, match="declared type"):
        _materialize_family_variant(case, [])


def test_tpcs_family_variant_column_collision_is_rejected() -> None:
    # A concrete subtype that declares a real column named `family_variant` collides
    # with the synthetic variant alias; the oracle rejects it with a clear diagnostic.
    case = _document_case("Document", {"all": {}})
    for definition in case.model.entity_defs:
        if definition["name"] == "Memo":
            definition["attributes"].append(
                {"name": "familyVariant", "type": "string", "column": "family_variant"}
            )
    with pytest.raises(CaseFailure, match="collides"):
        _materialize_family_variant(case, [])
