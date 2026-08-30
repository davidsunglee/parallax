"""Settling a write against the find its own unit of work named.

The corpus states the observed state in two independent places — the find's
``expectRows`` and the golden the write emits — and this is the arm that makes
them agree. Each degradation below moves ONE of those places and requires the
refusal to notice; each is asserted against a provider that raises on any call,
so every one of them is a defect of the document, refused before provisioning.
WHICH find a write may name is a different question, decided about the document
alone and asked of every case before any executor runs
(`tests/test_scenario_document.py`).

Two degradations of the harness itself discriminate these cross-checks. Emptying
the settled-write judgement must fail every one of them and nothing else.
Resolving the observed milestone from the group's LAST find instead of the NAMED
one — the identity-keying mistake the whole reference exists to catch — must fail
the authored case while letting the wrong-rectangle golden pass; that pair is what
shows the check reads the find the write named rather than any find.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from reference_harness.case import Case, Model, load_model
from reference_harness.case_assertions import CaseFailure
from reference_harness.unit_work_scenario import assert_unit_work_scenario

from .conftest import COMPATIBILITY_ROOT, RefusingProvider, assert_judged

_SETTLED = "m-unit-work-015-close-settles-against-the-milestone-its-own-find-observed.yaml"

_ACCOUNT_FIND = "select t0.id, t0.owner, t0.balance, t0.version from account t0 where t0.id = ?"
_ACCOUNTS_FIND = "select t0.id, t0.owner, t0.balance, t0.version from account t0"
_ANIMAL_FIND = (
    "select t0.id, t0.kind, t0.name, t0.owner_id, t0.license_id, t0.indoor, "
    "t0.bark_volume, t0.tusk_length from animal t0"
)
_RATE_UNION_FIND = (
    "select t0.id, t0.amount, t0.grade, cast(null as decimal(18, 2)) spread, t0.from_z, "
    "t0.thru_z, t0.in_z, t0.out_z, 'DepositRate' family_variant from deposit_rate t0 "
    "where t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ? union all select t0.id, "
    "t0.amount, cast(null as varchar(8)) grade, t0.spread, t0.from_z, t0.thru_z, t0.in_z, "
    "t0.out_z, 'LoanRate' family_variant from loan_rate t0 where t0.from_z <= ? and "
    "t0.thru_z > ? and t0.out_z = ?"
)
_DEPOSIT_RATE_FIND = (
    "select t0.id, t0.amount, t0.grade, t0.from_z, t0.thru_z, t0.in_z, t0.out_z "
    "from deposit_rate t0 where t0.thru_z = ? and t0.in_z <= ? and t0.out_z > ?"
)
_BALANCE_FIND = (
    "select t0.bal_id, t0.acct_num, t0.val, t0.in_z, t0.out_z from balance t0 where t0.bal_id = ?"
)


# --- the bitemporal close the corpus itself authors --------------------------


def test_the_authored_settled_close_agrees_with_the_milestone_its_find_observed(
    corpus_case,
) -> None:
    assert_judged(corpus_case(_SETTLED))


def test_a_close_binding_the_other_current_rectangle_is_refused(damaged_case) -> None:
    # The degradation the whole reference exists to catch: id 1 holds TWO current
    # rectangles, and this close addresses the one the named find did NOT return
    # (R3's Valid-Time end, `infinity`, instead of R2's 2024-06-01). An
    # implementation keying observations by identity alone renders exactly this
    # golden, so a cross-check that passed it would grade nothing.
    case = damaged_case(_SETTLED)
    case.when["scenario"][2]["statements"][0]["binds"][2] = "infinity"
    with pytest.raises(CaseFailure):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_close_binding_another_milestones_gate_is_refused(damaged_case) -> None:
    # The optimistic gate is derived from the SAME observed row as the address, so
    # a gate taken from anywhere else fails even while the address still agrees.
    case = damaged_case(_SETTLED)
    case.when["scenario"][2]["statements"][0]["binds"][4] = "2024-01-01T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        assert_unit_work_scenario(case, RefusingProvider())


def test_moving_what_the_named_find_observed_is_refused(damaged_case) -> None:
    # The other independent place: move what the named find declares it observed,
    # and the unchanged golden close no longer matches it. This is the half that
    # proves the cross-check reads the find's own result rather than re-deriving
    # the close from the golden it is comparing against.
    case = damaged_case(_SETTLED)
    case.when["scenario"][0]["expectRows"][0]["thru_z"] = "2024-05-01T00:00:00+00:00"
    with pytest.raises(CaseFailure):
        assert_unit_work_scenario(case, RefusingProvider())


def test_settling_against_a_find_that_observed_another_key_is_refused(damaged_case) -> None:
    # The named find MUST have observed a row of the write's own key; a reference
    # to a find that observed none names evidence that does not exist.
    case = damaged_case(_SETTLED)
    case.when["scenario"][0]["expectRows"][0]["pos_id"] = 2
    with pytest.raises(CaseFailure, match="observed 0 row"):
        assert_unit_work_scenario(case, RefusingProvider())


# --- the versioned Non-Temporal arm -----------------------------------------


def test_a_versioned_writes_gate_binds_the_named_generation() -> None:
    # A versioned Non-Temporal key holds one ROW but one observed GENERATION per
    # read, so the reference names which reading a write settled against and the
    # optimistic gate is where the difference lands. A golden binding a version
    # the named find never returned is the misresolution this catches.
    assert_judged(_versioned_settled_case(version=2))

    with pytest.raises(CaseFailure, match="observed version 2"):
        assert_unit_work_scenario(_versioned_settled_case(version=1), RefusingProvider())


def test_a_versioned_writes_advance_is_graded_under_locking() -> None:
    # Locking emits no gate, but the version advance is framework-computed from
    # the SAME observation under either strategy, so a locking golden still states
    # which generation the write settled against and is still cross-checked. The
    # advance is located by the version column's position in the golden's own SET
    # clause, never by assuming where a writer put it.
    assert_judged(_versioned_settled_case(version=2, concurrency="locking"))

    stale = _versioned_settled_case(version=1, concurrency="locking")
    with pytest.raises(CaseFailure, match="advances the version to 2"):
        assert_unit_work_scenario(stale, RefusingProvider())


def test_a_versioned_write_resolves_the_generation_of_its_own_key() -> None:
    # The named find MUST have observed a row of the WRITE's own key. A find that
    # returned several keys still answers for the one written — reducing its rows
    # to a version set would refuse this outright — while a find that returned
    # none of that key names evidence that does not exist, however many other
    # rows it carried at the matching version.
    several = [
        {"id": 1, "owner": "Ada", "balance": "125.00", "version": 2},
        {"id": 2, "owner": "Grace", "balance": "10.00", "version": 7},
    ]
    assert_judged(_versioned_settled_case(version=2, observed=several))

    unobserved = [{"id": 2, "owner": "Grace", "balance": "10.00", "version": 2}]
    with pytest.raises(CaseFailure, match="observed 0 row"):
        assert_unit_work_scenario(
            _versioned_settled_case(version=2, observed=unobserved), RefusingProvider()
        )


def test_a_versioned_writes_binds_are_read_for_the_executing_dialect() -> None:
    # `binds` carries the same dialect-keyed polymorphism `sql` does, so a golden
    # whose hole structure diverges answers with the executing dialect's own array
    # rather than with the keys of the map (m-case-format).
    assert_judged(_versioned_settled_case(version=2, dialect_keyed_binds=True))

    stale = _versioned_settled_case(version=1, dialect_keyed_binds=True)
    with pytest.raises(CaseFailure, match="observed version 2"):
        assert_unit_work_scenario(stale, RefusingProvider())


def test_a_versioned_writes_version_column_is_located_by_its_rendered_spelling() -> None:
    # A `column=` override may name a reserved physical column, which every
    # rendering quotes (python.md, m-dialect). Locating the advance by the model's
    # own unquoted name would report the framework version absent from a golden
    # that assigns it.
    assert_judged(_reserved_version_column_case(advance=3))

    with pytest.raises(CaseFailure, match="advances the version to 9"):
        assert_unit_work_scenario(_reserved_version_column_case(advance=9), RefusingProvider())


# --- aligning each entry with the statement its own object survives as -------


def test_each_object_is_graded_against_its_own_statement() -> None:
    # The buffer that expresses a coalescing pair equally expresses a mixed
    # multi-object flush (`m-unit-work`), whose objects emit one statement each.
    # Each is graded against the generation the named find observed of ITS OWN
    # key, so a golden gating one object on the other's version is refused.
    assert_judged(_multi_object_settled_case())

    with pytest.raises(CaseFailure, match="observed version 5"):
        assert_unit_work_scenario(_multi_object_settled_case(second_version=2), RefusingProvider())


def test_the_goldens_need_not_follow_the_entries_own_order() -> None:
    # A flush dependency-orders its surviving writes (`m-unit-work`), so the
    # statement order a legal buffer produces is the object graph's rather than
    # the author's — a parent's write may precede or follow the child's whichever
    # order the entries were written in. Each object is still graded against its
    # own statement, so reversing the golden list changes no verdict.
    case = _multi_object_settled_case()
    case.when["scenario"][1]["statements"].reverse()
    assert_judged(case)

    stale = _multi_object_settled_case(second_version=2)
    stale.when["scenario"][1]["statements"].reverse()
    with pytest.raises(CaseFailure, match="observed version 5"):
        assert_unit_work_scenario(stale, RefusingProvider())


def test_the_object_a_statement_settles_is_the_key_its_predicate_binds() -> None:
    # The object a statement settles is the key its identity predicate binds, not
    # any bind that happens to equal one: here the second UPDATE addresses account
    # 1 — which the first already settles — while carrying account 2's observed
    # generation, so it advances the version to the very 2 a search over its whole
    # bind row would take for account 2's key.
    case = _multi_object_settled_case()
    case.when["scenario"][0]["expectRows"][1]["version"] = 1
    case.when["scenario"][1]["statements"][1]["binds"] = ["60.00", 2, 1, 1]
    with pytest.raises(CaseFailure, match="2 existing-row statements addressing"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_a_settled_step_carries_one_existing_row_golden_per_object() -> None:
    case = _multi_object_settled_case()
    del case.when["scenario"][1]["statements"][1]
    case.when["scenario"][1]["roundTrips"] = 1
    case.then["roundTrips"] = 2
    with pytest.raises(CaseFailure, match="no existing-row statement"):
        assert_unit_work_scenario(case, RefusingProvider())

    extra = _multi_object_settled_case()
    extra.when["scenario"][1]["write"] = extra.when["scenario"][1]["write"][:1]
    with pytest.raises(CaseFailure, match="addressing an object no entry"):
        assert_unit_work_scenario(extra, RefusingProvider())


def test_a_settled_golden_must_open_its_predicate_with_a_bound_key() -> None:
    # The address is read at a POSITION — the predicate's leading bound key
    # equality — so a golden that opens with anything else states no object for its
    # binds to be read against, and is refused rather than silently offering some
    # other bind as its key. Here the leading predicate names a SET.
    case = _multi_object_settled_case()
    case.when["scenario"][1]["statements"][1]["sql"]["postgres"] = (
        "update account set balance = ?, version = ? where id in (?) and version = ?"
    )
    with pytest.raises(CaseFailure, match="does not open with a bound key equality"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_an_address_reads_each_identifier_with_its_own_quoting() -> None:
    # An address is compared to the model by the identifier the golden SPELLS. An
    # unquoted name is folded by the database, so it addresses the object however it
    # is cased and its canonical rendering is the folded one every other case here
    # carries; a QUOTED one keeps exactly what it spells (m-dialect), so a quoted
    # `"ACCOUNT"` / `"ID"` names a table and column this model does not declare.
    # Lowercasing both sides would read the two spellings as one identifier, and a
    # model declaring `"Order"` beside `order` would have its two objects' goldens
    # answer for each other.
    quoted = _versioned_settled_case(version=2)
    quoted.when["scenario"][1]["statements"][0]["sql"]["postgres"] = (
        'update "ACCOUNT" set balance = ?, version = ? where "ID" = ? and version = ?'
    )
    with pytest.raises(CaseFailure, match="no existing-row statement addressing"):
        assert_unit_work_scenario(quoted, RefusingProvider())


# --- which observed row a write of an inheritance family settled against -----


def test_a_write_of_a_shared_table_routes_to_its_own_subtype() -> None:
    # A table-per-hierarchy family shares one table, so the address a golden carries
    # names the object but not which concrete subtype claimed it. The tag guard is
    # what says that, and it binds the written subtype's own `tagValue`
    # (m-inheritance) — a settled Dog update guarded on `cat` writes rows this entry
    # never wrote.
    assert_judged(_shared_table_settled_case())

    with pytest.raises(CaseFailure, match="tagValue"):
        assert_unit_work_scenario(_shared_table_settled_case(tag="cat"), RefusingProvider())


def test_a_write_resolves_the_observed_row_of_its_own_variant() -> None:
    # A primary key names one object per TABLE, and only a table-per-hierarchy family
    # shares one: under table-per-concrete-subtype each concrete owns its own table, so
    # one discriminated-union read legitimately returns sibling rows of ONE key from
    # different tables (m-inheritance-052 authors exactly that result). Which of them a
    # settled write observed is the variant its own subtype names — resolving by key
    # alone would refuse this legal case as two observed states.
    assert_judged(_polymorphic_settled_case())

    sibling_rectangle = _polymorphic_settled_case(
        valid_end="infinity", tx_start="2024-03-01T00:00:00+00:00"
    )
    with pytest.raises(CaseFailure):
        assert_unit_work_scenario(sibling_rectangle, RefusingProvider())


def test_a_write_is_not_settled_by_a_sibling_variants_row() -> None:
    # The other half of the same rule: a find that returned the SIBLING at this key
    # observed nothing about the written object, so the reference names evidence that
    # does not exist. Matching by key alone would hand the DepositRate close LoanRate's
    # own rectangle and grade the golden green against it.
    case = _polymorphic_settled_case(observed_variants=("LoanRate",))
    with pytest.raises(CaseFailure, match="observed 0 row"):
        assert_unit_work_scenario(case, RefusingProvider())


def test_variant_resolution_reads_the_finds_own_discriminator() -> None:
    # `family_variant` and `familyVariant` are the spellings a DISCRIMINATED read states
    # its variant in, and both are equally legal PHYSICAL spellings for a model to author
    # (the corpus maps `catalog.Record.variantMarker` to the column `family_variant`). So
    # what a field of either spelling means is the origin read's question, not the field's:
    # a concrete-target find carries no discriminator at all (m-sql), so its row's
    # `family_variant` is the model's own column and says nothing about the variant; an
    # abstract find's materialized `familyVariant` is its answer, and the physical column
    # remapped back beside it is not. Reading the physical column as the tag refuses the
    # first two settlements outright and, worse, lets a domain value equal to a variant
    # spelling overrule the read's own answer and license the sibling's rectangle.
    assert_judged(
        _physical_variant_column_settled_case(
            target="parallax.compatibility.DepositRate",
            discriminators={"family_variant": "catalog-marker"},
        )
    )
    assert_judged(
        _physical_variant_column_settled_case(
            target="parallax.compatibility.Rate",
            discriminators={"family_variant": "catalog-marker", "familyVariant": "DepositRate"},
        )
    )

    overruled = _physical_variant_column_settled_case(
        target="parallax.compatibility.Rate",
        discriminators={"family_variant": "DepositRate", "familyVariant": "LoanRate"},
    )
    with pytest.raises(CaseFailure, match="observed 0 row"):
        assert_unit_work_scenario(overruled, RefusingProvider())


# --- the Transaction-Time-Only arm ------------------------------------------


def test_a_transaction_time_only_target_settles_against_its_named_find() -> None:
    # The arm an "is it temporal?" test cannot reach and a Bitemporal-only
    # restriction would deny. A Transaction-Time-Only key is read at as-of
    # Transaction-Time coordinates resolving to milestones of any age, so this
    # group holds two pieces of evidence about one key and the close settles
    # against the one its named find returned. Naming the OTHER find — the
    # historical milestone an identity-keyed store would leave in the single slot —
    # leaves the same golden gate binding a milestone the write was not handed.
    assert_judged(_transaction_time_only_settled_case(on=0))

    with pytest.raises(CaseFailure):
        assert_unit_work_scenario(_transaction_time_only_settled_case(on=1), RefusingProvider())


# --- the cases the corpus does not carry ------------------------------------


def _case(raw: dict[str, Any], model: Model, stem: str) -> Case:
    return Case(path=Path(f"{stem}.yaml"), raw=raw, model=model)


def _account_model() -> Model:
    return load_model(COMPATIBILITY_ROOT, "models/account.yaml")


def _versioned_settled_case(
    *,
    version: int,
    concurrency: str = "optimistic",
    observed: list[dict[str, Any]] | None = None,
    dialect_keyed_binds: bool = False,
) -> Case:
    """A `uow` group that observes Account 1 at version 2 and then updates it,
    with the golden advancing from — and, under optimistic concurrency, gating
    on — *version*."""
    gated = concurrency == "optimistic"
    sql = "update account set balance = ?, version = ? where id = ?"
    binds: Any = ["175.00", version + 1, 1, version] if gated else ["175.00", version + 1, 1]
    gated_sql = f"{sql} and version = ?" if gated else sql
    statement: dict[str, Any] = {"sql": {"postgres": gated_sql}, "binds": binds}
    if dialect_keyed_binds:
        statement = {
            "sql": {"postgres": gated_sql, "mariadb": gated_sql},
            "binds": {"postgres": binds, "mariadb": binds},
        }
    raw: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": concurrency},
            "scenario": [
                {
                    "uow": "generations",
                    "objectQuery": {
                        "target": "parallax.compatibility.Account",
                        "predicate": {
                            "eq": {"attr": "parallax.compatibility.Account.id", "value": 1}
                        },
                    },
                    "roundTrips": 1,
                    "statements": [{"sql": {"postgres": _ACCOUNT_FIND}, "binds": [1]}],
                    "expectRows": (
                        [{"id": 1, "owner": "Ada", "balance": "125.00", "version": 2}]
                        if observed is None
                        else observed
                    ),
                },
                {
                    "uow": "generations",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 1, "balance": "175.00"}],
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [statement],
                },
            ],
        },
        "then": {"roundTrips": 2},
    }
    return _case(raw, _account_model(), "m-unit-work-996-synthetic")


def _reserved_version_column_case(*, advance: int) -> Case:
    """The same versioned settlement over a model whose optimistic-lock Attribute
    is stored in the reserved physical column ``order``, which every rendering
    quotes."""
    model = copy.deepcopy(_account_model())
    version = next(
        attribute
        for attribute in model.entity_defs[0]["attributes"]
        if attribute.get("optimisticLocking")
    )
    version["column"] = "order"
    find = 'select t0.id, t0.owner, t0.balance, t0."order" from account t0 where t0.id = ?'
    update = 'update account set balance = ?, "order" = ? where id = ? and "order" = ?'
    raw: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                {
                    "uow": "reserved",
                    "objectQuery": {
                        "target": "parallax.compatibility.Account",
                        "predicate": {
                            "eq": {"attr": "parallax.compatibility.Account.id", "value": 1}
                        },
                    },
                    "roundTrips": 1,
                    "statements": [{"sql": {"postgres": find}, "binds": [1]}],
                    "expectRows": [{"id": 1, "owner": "Ada", "balance": "125.00", "order": 2}],
                },
                {
                    "uow": "reserved",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 1, "balance": "175.00"}],
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {"sql": {"postgres": update}, "binds": ["175.00", advance, 1, 2]}
                    ],
                },
            ],
        },
        "then": {"roundTrips": 2},
    }
    return _case(raw, model, "m-unit-work-992-synthetic")


def _multi_object_settled_case(*, second_version: int = 5) -> Case:
    """A `uow` group whose one find observes Accounts 1 and 2, and whose write
    step buffers an update of each — the mixed multi-object flush the buffered
    keyed form equally expresses, settling both against that one find."""
    update = "update account set balance = ?, version = ? where id = ? and version = ?"
    raw: dict[str, Any] = {
        "model": "models/account.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                {
                    "uow": "two-objects",
                    "objectQuery": {"target": "parallax.compatibility.Account"},
                    "roundTrips": 1,
                    "statements": [{"sql": {"postgres": _ACCOUNTS_FIND}, "binds": []}],
                    "expectRows": [
                        {"id": 1, "owner": "Ada", "balance": "100.00", "version": 2},
                        {"id": 2, "owner": "Grace", "balance": "50.00", "version": 5},
                    ],
                },
                {
                    "uow": "two-objects",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 1, "balance": "175.00"}],
                        },
                        {
                            "mutation": "update",
                            "entity": "Account",
                            "rows": [{"id": 2, "balance": "60.00"}],
                        },
                    ],
                    "roundTrips": 2,
                    "statements": [
                        {"sql": {"postgres": update}, "binds": ["175.00", 3, 1, 2]},
                        {
                            "sql": {"postgres": update},
                            "binds": ["60.00", second_version + 1, 2, second_version],
                        },
                    ],
                },
            ],
        },
        "then": {"roundTrips": 3},
    }
    return _case(raw, _account_model(), "m-unit-work-995-synthetic")


def _shared_table_settled_case(*, tag: str = "dog") -> Case:
    """A `uow` group whose find observes Animal 1 and whose write settles an update
    of the concrete subtype Dog against it, on the family's shared table."""
    raw: dict[str, Any] = {
        "model": "models/animal.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "scenario": [
                {
                    "uow": "shared-table",
                    "objectQuery": {"target": "parallax.compatibility.Animal"},
                    "roundTrips": 1,
                    "statements": [{"sql": {"postgres": _ANIMAL_FIND}, "binds": []}],
                    "expectRows": [{"id": 1, "name": "Rex", "familyVariant": "Dog"}],
                },
                {
                    "uow": "shared-table",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "parallax.compatibility.Dog",
                            "rows": [{"id": 1, "barkVolume": 9}],
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update animal set bark_volume = ? "
                                "where id = ? and kind = ?"
                            },
                            "binds": [9, 1, tag],
                        }
                    ],
                },
            ],
        },
        "then": {"roundTrips": 2},
    }
    return _case(
        raw, load_model(COMPATIBILITY_ROOT, "models/animal.yaml"), "m-unit-work-994-synthetic"
    )


def _physical_variant_column_settled_case(*, target: str, discriminators: dict[str, Any]) -> Case:
    """The settled bitemporal close of DepositRate 1 over a Rate family that ALSO declares
    a physical ``family_variant`` column of its own, observed by a find whose queried
    position is *target* and whose one row carries *discriminators* beside its payload."""
    model = copy.deepcopy(load_model(COMPATIBILITY_ROOT, "models/rate.yaml"))
    model.descriptor["entities"][0]["attributes"].append(
        {"name": "variantMarker", "type": "string", "maxLength": 64, "column": "family_variant"}
    )
    row = {
        "id": 1,
        "amount": "2.50",
        "grade": "A",
        "from_z": "2024-01-01T00:00:00+00:00",
        "thru_z": "2024-06-01T00:00:00+00:00",
        "in_z": "2024-02-01T00:00:00+00:00",
        "out_z": "infinity",
        **discriminators,
    }
    return _settled_close_case(target=target, expect_rows=[row], model=model)


def _polymorphic_settled_case(
    *,
    valid_end: str = "2024-06-01T00:00:00+00:00",
    tx_start: str = "2024-02-01T00:00:00+00:00",
    observed_variants: tuple[str, ...] = ("DepositRate", "LoanRate"),
) -> Case:
    """A `uow` group whose abstract-root find over the table-per-concrete-subtype Rate
    family observes DepositRate 1 and LoanRate 1 — one key, two tables — and whose
    write settles a bitemporal close of DepositRate 1 against it."""
    rows = {
        "DepositRate": {
            "id": 1,
            "amount": "2.50",
            "grade": "A",
            "from_z": "2024-01-01T00:00:00+00:00",
            "thru_z": "2024-06-01T00:00:00+00:00",
            "in_z": "2024-02-01T00:00:00+00:00",
            "out_z": "infinity",
            "family_variant": "DepositRate",
        },
        "LoanRate": {
            "id": 1,
            "amount": "6.75",
            "spread": "1.25",
            "from_z": "2024-01-01T00:00:00+00:00",
            "thru_z": "infinity",
            "in_z": "2024-03-01T00:00:00+00:00",
            "out_z": "infinity",
            "family_variant": "LoanRate",
        },
    }
    return _settled_close_case(
        target="parallax.compatibility.Rate",
        expect_rows=[rows[variant] for variant in observed_variants],
        valid_end=valid_end,
        tx_start=tx_start,
    )


def _settled_close_case(
    *,
    target: str,
    expect_rows: list[dict[str, Any]],
    valid_end: str = "2024-06-01T00:00:00+00:00",
    tx_start: str = "2024-02-01T00:00:00+00:00",
    model: Model | None = None,
) -> Case:
    """A `uow` group whose find at the queried position *target* observes *expect_rows*
    and whose write settles a bitemporal close of DepositRate 1 against it."""
    at = "2024-10-01T00:00:00+00:00"
    abstract = target.endswith(".Rate")
    find = _RATE_UNION_FIND if abstract else _DEPOSIT_RATE_FIND
    as_of = ["2024-06-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00", "infinity"]
    raw: dict[str, Any] = {
        "model": "models/rate.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                {
                    "uow": "polymorphic",
                    "objectQuery": {"target": target},
                    "roundTrips": 1,
                    "statements": [
                        {"sql": {"postgres": find}, "binds": as_of * 2 if abstract else as_of}
                    ],
                    "expectRows": expect_rows,
                },
                {
                    "uow": "polymorphic",
                    "on": 0,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "parallax.compatibility.DepositRate",
                            "rows": [{"id": 1, "amount": "3.00"}],
                            "validFrom": "2024-03-01T00:00:00+00:00",
                            "at": at,
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update deposit_rate set out_z = ? "
                                "where id = ? and thru_z = ? and out_z = ? and in_z = ?"
                            },
                            "binds": [at, 1, valid_end, "infinity", tx_start],
                        }
                    ],
                },
            ],
        },
        "then": {"roundTrips": 2},
    }
    return _case(
        raw,
        model if model is not None else load_model(COMPATIBILITY_ROOT, "models/rate.yaml"),
        "m-unit-work-993-synthetic",
    )


def _transaction_time_only_settled_case(*, on: int) -> Case:
    """A `uow` group that reads a Transaction-Time-Only key's CURRENT milestone,
    reads the SAME key as of an earlier Transaction-Time instant, then closes the
    milestone step *on* returned.

    Only one of Balance id 1's milestones is current, but both reads are evidence,
    and the golden close's gate binds the observed milestone's own ``in_z``. Its
    address carries no Valid-Time half — a Transaction-Time-Only close addresses the
    key plus the invariant open bound — so the gate is the whole of what states
    which milestone was settled against.
    """
    raw: dict[str, Any] = {
        "model": "models/balance.yaml",
        "tags": ["m-unit-work"],
        "shape": "scenario",
        "when": {
            "uow": {"concurrency": "optimistic"},
            "scenario": [
                _balance_find(1, "2024-04-01T00:00:00+00:00", "infinity", 100.00),
                _balance_find(1, "2024-01-01T00:00:00+00:00", "2024-04-01T00:00:00+00:00", 90.00),
                {
                    "uow": "observe-then-close",
                    "on": on,
                    "write": [
                        {
                            "mutation": "update",
                            "entity": "Balance",
                            "rows": [{"id": 1, "value": 150.00}],
                            "at": "2024-10-01T00:00:00+00:00",
                        }
                    ],
                    "roundTrips": 1,
                    "statements": [
                        {
                            "sql": {
                                "postgres": "update balance set out_z = ? where bal_id = ? "
                                "and out_z = ? and in_z = ?"
                            },
                            "binds": [
                                "2024-10-01T00:00:00+00:00",
                                1,
                                "infinity",
                                "2024-04-01T00:00:00+00:00",
                            ],
                        }
                    ],
                },
            ],
        },
        "then": {"roundTrips": 3},
    }
    return _case(
        raw, load_model(COMPATIBILITY_ROOT, "models/balance.yaml"), "m-unit-work-997-synthetic"
    )


def _balance_find(pk: int, tx_start: str, tx_end: Any, value: float) -> dict[str, Any]:
    return {
        "uow": "observe-then-close",
        "objectQuery": {
            "target": "Balance",
            "predicate": {"eq": {"attr": "Balance.id", "value": pk}},
        },
        "roundTrips": 1,
        "statements": [{"sql": {"postgres": _BALANCE_FIND}, "binds": [pk]}],
        "expectRows": [
            {
                "bal_id": pk,
                "acct_num": "A",
                "val": value,
                "in_z": tx_start,
                "out_z": tx_end,
            }
        ],
    }
