"""Unit Work Scenario reads through ``ScenarioReads.assert_step``.

One instance per Compatibility Case, one call per read-bearing step, and nothing
else crossing the seam: the operation takes an index and a reader, and reads the
rest of its intent out of the step the case authored.

What the group proves is that the four workflows behind that one operation stay
behaviorally distinct. A query and a resolving load issue exactly the statements
their step lists; a reuse and an already-materialized access issue none at all,
which is asserted by the scripted adapter's call list not growing across the step.
The rows a script hands back are PHYSICAL, so every passing test is also a test
that the oracle derived the logical result the step's own ``expectRows`` states.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from reference_harness.case import Case
from reference_harness.case_assertions import CaseFailure
from reference_harness.object_query_oracle import ScenarioReads

from .conftest import ScriptedReads

CaseLoader = Callable[[str], Case]

_CONSTRUCTION = "m-op-list-001-construction-first-access-reaccess.yaml"
_POPULATED_LIST = "m-op-list-002-deep-fetch-population-stable.yaml"
_VALUE_OBJECT_LIST = "m-op-list-004-first-access-divergent-value-object-list.yaml"
_EDIT_KEEPS_ITEMS = "m-snapshot-read-016-edit-keeps-loaded-items.yaml"
_MULTI_HOP_ACCESS = "m-snapshot-read-026-multi-hop-access-drops-null-branches.yaml"
_READ_YOUR_OWN_WRITES = "m-unit-work-029-ryow-relationship.yaml"
_STREAMED_EVIDENCE = "m-unit-work-030-a-streamed-roots-evidence-licenses-a-later-write.yaml"
_ABSTRACT_FIND = "m-inheritance-130-tph-abstract-find-licenses-concrete-update.yaml"
_RESOLVING_READ = "m-bitemp-write-010-predicate-plain-update-materialize.yaml"
_ONE_OBJECT_TWO_FINDS = "m-identity-map-001-same-transaction-identity.yaml"
_TPCS_ABSTRACT_READ = "m-inheritance-050-tpcs-abstract-root-read.yaml"


def _order(
    id_: int, name: str, sku: str | None, qty: int, price: str, active: bool, ordered_on: str
) -> dict[str, Any]:
    return {
        "id": id_,
        "name": name,
        "sku": sku,
        "qty": qty,
        "price": Decimal(price),
        "active": active,
        "ordered_on": ordered_on,
    }


_ORDERS: list[dict[str, Any]] = [
    _order(1, "Ada", "A-100", 5, "10.50", True, "2024-01-05"),
    _order(2, "Linus", "B-200", 10, "20.00", True, "2024-02-10"),
    _order(3, "ada", "A-300", 15, "30.25", False, "2024-03-15"),
    _order(4, "Margaret", None, 20, "40.00", True, "2024-04-20"),
    _order(5, "Alan", "C_50%", 25, "50.75", False, "2024-05-25"),
    _order(42, "Grace", "A-999", 30, "99.99", True, "2024-06-30"),
]
_ORDER_ONE = [_ORDERS[0]]

_ALL_ITEMS: list[dict[str, Any]] = [
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
    {"id": 21, "order_id": 2, "sku": "A-300", "quantity": 4, "shipped_on": "2024-02-20"},
    {"id": 421, "order_id": 42, "sku": "A-999", "quantity": 3, "shipped_on": "2024-03-10"},
    {"id": 422, "order_id": 42, "sku": "B-200", "quantity": 5, "shipped_on": "2024-02-05"},
]

# `Order.items` declares `id desc`, so a child level must return 12 before 11.
_ORDER_ONE_ITEMS: list[dict[str, Any]] = [
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
]

# Status 101 is order-level, so its `order_item_id` is null and its branch reaches
# no item; 201 and 202 both reach item 11, and 203 reaches item 12.
_ORDER_ONE_STATUSES: list[dict[str, Any]] = [
    {"id": 101, "order_id": 1, "order_item_id": None, "code": "placed"},
    {"id": 201, "order_id": 1, "order_item_id": 11, "code": "packed"},
    {"id": 202, "order_id": 1, "order_item_id": 11, "code": "shipped"},
    {"id": 203, "order_id": 1, "order_item_id": 12, "code": "packed"},
]
_STATUS_ITEMS: list[dict[str, Any]] = [
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": "2024-02-15"},
]


def _account(id_: int, owner: str, balance: str, version: int) -> dict[str, Any]:
    return {"id": id_, "owner": owner, "balance": Decimal(balance), "version": version}


_LINUS = [_account(2, "Linus", "250.00", 1)]

_FIRST_DELIVERY = [
    [_account(1, "Ada", "100.00", 1), _account(2, "Linus", "250.00", 1)],
    [_account(3, "Grace", "10.00", 1)],
    [
        _account(1, "Ada", "100.00", 1),
        _account(2, "Linus", "250.00", 1),
        _account(3, "Grace", "10.00", 1),
    ],
]
_SECOND_DELIVERY = [
    [_account(1, "Ada", "125.00", 2), _account(2, "Linus", "250.00", 1)],
    [_account(3, "Grace", "10.00", 1)],
    [
        _account(1, "Ada", "125.00", 2),
        _account(2, "Linus", "250.00", 1),
        _account(3, "Grace", "10.00", 1),
    ],
]

_LATEST_POSITION: list[dict[str, Any]] = [
    {
        "pos_id": 1,
        "acct_num": "A",
        "val": Decimal("200.00"),
        "from_z": "2024-06-01T00:00:00+00:00",
        "thru_z": "infinity",
        "in_z": "2024-04-01T00:00:00+00:00",
        "out_z": "infinity",
    }
]

_STEPS_KEY = "scenario"


def _steps(case: Case) -> list[dict[str, Any]]:
    return case.when[_STEPS_KEY]


# --- the interface itself ----------------------------------------------------


def test_the_oracle_exposes_one_scenario_operation_and_no_retained_type() -> None:
    """The whole Scenario seam is one method, and no observation type escapes it.

    A retained observation has no public type, constructor, fields, or iteration:
    it is recorded and read entirely inside one instance, so orchestration cannot
    reach a row, a view, or an identity it did not ask a step for.
    """
    import reference_harness.object_query_oracle as oracle

    assert sorted(oracle.__all__) == ["ReadExecutor", "ScenarioReads", "assert_case_read"]
    public = sorted(name for name in vars(ScenarioReads) if not name.startswith("_"))
    assert public == ["assert_step"]


def test_a_step_index_outside_the_scenario_is_refused(corpus_case: CaseLoader) -> None:
    reads = ScenarioReads(corpus_case(_CONSTRUCTION))

    with pytest.raises(CaseFailure, match=r"scenario\[7\] is not a step of this case"):
        reads.assert_step(7, ScriptedReads())


def test_a_step_asserted_twice_is_refused(corpus_case: CaseLoader) -> None:
    """A second assertion would replace the observation the naming steps read."""
    reads = ScenarioReads(corpus_case(_CONSTRUCTION))
    reads.assert_step(1, ScriptedReads(results=[_ORDERS]))

    with pytest.raises(CaseFailure, match=r"scenario\[1\] is asserted twice"):
        reads.assert_step(1, ScriptedReads(results=[_ORDERS]))


def test_a_step_that_failed_an_observable_publishes_nothing(damaged_case: CaseLoader) -> None:
    """Publication is the last thing a step does, so a failed step retains nothing.

    Retaining before the observables are graded would hand a later step rows no
    comparison accepted, and would meet a second attempt at the failed step with
    "asserted twice" — a duplicate refusal standing in for the real failure.
    """
    case = damaged_case(_ONE_OBJECT_TWO_FINDS)
    _steps(case)[0]["expectRows"][0]["owner"] = "Someone else"
    reads = ScenarioReads(case)

    for _attempt in range(2):
        with pytest.raises(CaseFailure, match=r"scenario\[0\] rows != expectRows"):
            reads.assert_step(0, ScriptedReads(results=[_LINUS]))

    with pytest.raises(CaseFailure, match="names step 0, which published no observation"):
        reads.assert_step(1, ScriptedReads(results=[_LINUS]))


def test_a_write_step_is_not_this_oracles_to_assert(corpus_case: CaseLoader) -> None:
    reads = ScenarioReads(corpus_case(_STREAMED_EVIDENCE))
    reader = ScriptedReads()

    with pytest.raises(CaseFailure, match=r"scenario\[1\] is a write step"):
        reads.assert_step(1, reader)
    assert reader.calls == []


def test_a_non_read_verb_action_step_is_not_this_oracles_to_assert(
    corpus_case: CaseLoader,
) -> None:
    """A `mutate` observes no rows, so grading it here would grade nothing."""
    reads = ScenarioReads(corpus_case(_EDIT_KEEPS_ITEMS))

    with pytest.raises(CaseFailure, match=r"scenario\[1\] is a 'mutate' action step"):
        reads.assert_step(1, ScriptedReads())


def test_an_unresolved_list_construction_is_not_this_oracles_to_assert(
    corpus_case: CaseLoader,
) -> None:
    """Constructing a query-backed list stays with orchestration, and reads nothing.

    Its Object Query is still reachable from the case, which is how the step that
    first accesses the list resolves it — but there is no step of its own to
    assert, because it published nothing.
    """
    reads = ScenarioReads(corpus_case(_CONSTRUCTION))
    reader = ScriptedReads()

    with pytest.raises(CaseFailure, match="constructs a query-backed list that has not resolved"):
        reads.assert_step(0, reader)
    assert reader.calls == []


# --- a find -------------------------------------------------------------------


def test_a_find_runs_its_own_golden_and_grades_its_expectRows(corpus_case: CaseLoader) -> None:
    reads = ScenarioReads(corpus_case(_POPULATED_LIST))
    reader = ScriptedReads(results=[_ORDERS])

    reads.assert_step(0, reader)

    assert reader.calls == [
        (
            "select t0.id, t0.name, t0.sku, t0.qty, t0.price, t0.active, t0.ordered_on "
            "from orders t0",
            (),
        )
    ]


def test_a_find_whose_rows_disagree_with_expectRows_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_POPULATED_LIST)
    _steps(case)[0]["expectRows"][0]["name"] = "Someone else"
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match=r"scenario\[0\] rows != expectRows"):
        reads.assert_step(0, ScriptedReads(results=[_ORDERS]))


def test_a_finds_reference_oracle_runs_on_the_reader_the_golden_used(
    corpus_case: CaseLoader,
) -> None:
    """Both statements land on the ONE executor the step was handed.

    A grouped find reads through its group's held session, so an independent
    oracle taken on a fresh connection would observe committed-only state after
    an uncommitted grouped write and silently break the equivalence contract.
    """
    reads = ScenarioReads(corpus_case(_RESOLVING_READ))
    reader = ScriptedReads(results=[_LATEST_POSITION, _LATEST_POSITION])

    reads.assert_step(0, reader)

    assert len(reader.calls) == 2
    assert reader.statements[1].startswith("select pos_id, acct_num, val")


def test_a_find_whose_reference_oracle_disagrees_is_refused(corpus_case: CaseLoader) -> None:
    other = [{**_LATEST_POSITION[0], "val": Decimal("999.00")}]
    reads = ScenarioReads(corpus_case(_RESOLVING_READ))

    with pytest.raises(CaseFailure, match=r"scenario\[0\] referenceSql rows != golden rows"):
        reads.assert_step(0, ScriptedReads(results=[_LATEST_POSITION, other]))


def test_a_materializing_predicate_writes_resolving_read_is_an_ordinary_step(
    corpus_case: CaseLoader,
) -> None:
    """Nothing in the step distinguishes it, so nothing routes it differently.

    A predicate write's resolving read is authored as an ordinary preceding read —
    its own query, golden, reference oracle, and ``expectRows`` — and is graded
    the way every other Scenario read is. The exception it carries is the
    conformance adapter's (it publishes no ``stepRows`` entry), which the harness
    never expresses.
    """
    case = corpus_case(_RESOLVING_READ)
    assert "write" in _steps(case)[1]
    reads = ScenarioReads(case)

    reads.assert_step(0, ScriptedReads(results=[_LATEST_POSITION, _LATEST_POSITION]))


def test_an_abstract_target_step_publishes_familyVariant_not_the_raw_tag(
    corpus_case: CaseLoader,
) -> None:
    """The golden projects `kind`; the step's `expectRows` states `familyVariant: Car`."""
    physical = [{"id": 1, "kind": "car", "name": "Sedan", "version": 5, "doors": 4, "axles": None}]
    reads = ScenarioReads(corpus_case(_ABSTRACT_FIND))

    reads.assert_step(0, ScriptedReads(results=[physical]))


def _as_a_one_step_scenario(case: Case) -> Case:
    """A shipped `read` case restated as the Scenario step it would be authored as.

    A Scenario states its reads under the step and nothing at the top level, so a
    corpus read case is the closest thing to an authored step there is: its target,
    goldens, and expected rows move under ``when.scenario[0]`` unchanged.
    """
    read = case.raw["when"]["objectQuery"]
    statements = case.raw["then"]["statements"]
    rows = case.raw["then"]["rows"]
    case.raw["shape"] = "scenario"
    case.raw["when"] = {
        "scenario": [{"objectQuery": read, "statements": statements, "expectRows": rows}]
    }
    case.raw["then"] = {}
    return case


_DOCUMENT_FAMILY: list[dict[str, Any]] = [
    {
        "id": 1,
        "title": "Invoice-A",
        "folder_id": 100,
        "currency": "USD",
        "amount_due": Decimal("120.00"),
        "body": None,
        "paid_amount": None,
        "family_variant": "Invoice",
    },
    {
        "id": 2,
        "title": "Invoice-B",
        "folder_id": 101,
        "currency": "EUR",
        "amount_due": Decimal("80.00"),
        "body": None,
        "paid_amount": None,
        "family_variant": "Invoice",
    },
    {
        "id": 1,
        "title": "Memo-A",
        "folder_id": 102,
        "currency": None,
        "amount_due": None,
        "body": "Reminder",
        "paid_amount": None,
        "family_variant": "Memo",
    },
    {
        "id": 1,
        "title": "Receipt-A",
        "folder_id": 100,
        "currency": "USD",
        "amount_due": None,
        "body": None,
        "paid_amount": Decimal("120.00"),
        "family_variant": "Receipt",
    },
]


def test_a_table_per_concrete_subtype_step_materializes_against_its_own_read(
    damaged_case: CaseLoader,
) -> None:
    """A `union all` abstract step is graded against the read the STEP presents.

    Unlike the table-per-hierarchy step beside it, this materialization reads the
    query's own narrowing, ordering, cap, goldens, and binds to grade the branch
    and projection shape it renames `family_variant` out of — none of which a
    Scenario case carries at the top level, where a whole-case read states them.
    """
    reads = ScenarioReads(_as_a_one_step_scenario(damaged_case(_TPCS_ABSTRACT_READ)))

    reads.assert_step(0, ScriptedReads(results=[_DOCUMENT_FAMILY]))


def test_a_find_listing_sql_for_levels_its_query_declares_none_of_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_POPULATED_LIST)
    _steps(case)[0]["statements"].append(copy.deepcopy(_steps(case)[1]["statements"][0]))
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match="its objectQuery declares no `includes`"):
        reads.assert_step(0, ScriptedReads(results=[_ORDERS]))


# --- a find with Include Paths, and the graph it materialized -----------------


def test_a_read_step_states_the_graph_its_own_levels_materialized(
    corpus_case: CaseLoader,
) -> None:
    """`expectGraph` at its READ placement grades a materialization, not a survival."""
    reads = ScenarioReads(corpus_case(_READ_YOUR_OWN_WRITES))
    reader = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS])

    reads.assert_step(0, reader)

    assert len(reader.calls) == 2


def test_a_read_step_graph_that_disagrees_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_READ_YOUR_OWN_WRITES)
    _steps(case)[0]["expectGraph"]["Order"][0]["items"].pop()
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match=r"scenario\[0\] materialized graph != expectGraph"):
        reads.assert_step(0, ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS]))


def test_a_read_step_declaring_expectGraph_without_includes_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """The contents a read step states are the ones its OWN Include Paths fetched."""
    case = damaged_case(_POPULATED_LIST)
    _steps(case)[0]["expectGraph"] = {"Order": []}
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match="carries no `objectQuery.includes`"):
        reads.assert_step(0, ScriptedReads(results=[_ORDERS]))


# --- a relationship load ------------------------------------------------------


def test_a_load_resolves_its_levels_and_publishes_the_rows_they_returned(
    corpus_case: CaseLoader,
) -> None:
    """A deferred fetch batches the whole parent set into ONE child statement."""
    reads = ScenarioReads(corpus_case(_POPULATED_LIST))
    reader = ScriptedReads(results=[_ORDERS, _ALL_ITEMS])

    reads.assert_step(0, reader)
    reads.assert_step(1, reader)

    assert len(reader.calls) == 2
    assert reader.calls[1][1] == (1, 2, 3, 4, 5, 42)


def test_a_load_naming_a_source_that_is_not_earlier_is_refused(damaged_case: CaseLoader) -> None:
    case = damaged_case(_POPULATED_LIST)
    _steps(case)[1]["on"] = 1
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_ORDERS, _ALL_ITEMS])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match=r"scenario\[1\].on references step 1"):
        reads.assert_step(1, reader)


# --- an access over an already-materialized view ------------------------------


def test_an_access_over_a_materialized_view_issues_no_sql(corpus_case: CaseLoader) -> None:
    """A snapshot is closed-world, so a populated relationship is never re-read."""
    reads = ScenarioReads(corpus_case(_EDIT_KEEPS_ITEMS))
    reader = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS])
    reads.assert_step(0, reader)
    materialized = list(reader.calls)

    reads.assert_step(2, reader)

    assert reader.calls == materialized


def test_an_access_states_the_contents_the_source_read_materialized(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_EDIT_KEEPS_ITEMS)
    _steps(case)[2]["expectGraph"]["OrderItem"].pop()
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match=r"scenario\[2\] relationship contents != expectGraph"):
        reads.assert_step(2, reader)


def test_a_multi_hop_access_drops_the_branches_that_reached_no_row(
    corpus_case: CaseLoader,
) -> None:
    """Item 11 twice, because two statuses reach it; no null for the order-level one."""
    reads = ScenarioReads(corpus_case(_MULTI_HOP_ACCESS))
    reader = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_STATUSES, _STATUS_ITEMS])
    reads.assert_step(0, reader)
    materialized = list(reader.calls)

    reads.assert_step(1, reader)

    assert reader.calls == materialized


def test_an_access_naming_a_relationship_the_read_never_included_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_EDIT_KEEPS_ITEMS)
    _steps(case)[2]["path"] = "statuses"
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_ORDER_ONE, _ORDER_ONE_ITEMS])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match="the source read did not include 'statuses'"):
        reads.assert_step(2, reader)


# --- a named reuse ------------------------------------------------------------


def test_a_named_reuse_returns_the_rows_its_source_published_without_sql(
    corpus_case: CaseLoader,
) -> None:
    reads = ScenarioReads(corpus_case(_POPULATED_LIST))
    reader = ScriptedReads(results=[_ORDERS, _ALL_ITEMS])
    reads.assert_step(0, reader)
    reads.assert_step(1, reader)
    resolved = list(reader.calls)

    reads.assert_step(2, reader)

    assert reader.calls == resolved


def test_a_reuse_naming_a_step_that_is_not_earlier_is_refused(damaged_case: CaseLoader) -> None:
    """An empty reuse would let the step's identity assertion pass against nothing."""
    case = damaged_case(_POPULATED_LIST)
    _steps(case)[2]["sameObjectAs"] = 2
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_ORDERS, _ALL_ITEMS])
    reads.assert_step(0, reader)
    reads.assert_step(1, reader)

    with pytest.raises(CaseFailure, match="reuses prior rows from an UNRESOLVED source"):
        reads.assert_step(2, reader)


def test_a_reuse_naming_a_step_that_published_nothing_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A write publishes no observation, so no later step may read one off it."""
    case = damaged_case(_STREAMED_EVIDENCE)
    del _steps(case)[2]["stream"]
    del _steps(case)[2]["statements"]
    del _steps(case)[2]["referenceSql"]
    _steps(case)[2]["sameObjectAs"] = 1
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[*_FIRST_DELIVERY])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match="names step 1, which published no observation"):
        reads.assert_step(2, reader)


def test_two_finds_declared_to_denote_one_object_are_checked_on_identity(
    corpus_case: CaseLoader,
) -> None:
    """Two independent queries, one managed object: `sameObjectAs` grades the PKs."""
    reads = ScenarioReads(corpus_case(_ONE_OBJECT_TWO_FINDS))
    reader = ScriptedReads(results=[_LINUS, _LINUS])

    reads.assert_step(0, reader)
    reads.assert_step(1, reader)

    assert len(reader.calls) == 2


def test_two_finds_reaching_different_rows_break_the_one_object_rule(
    damaged_case: CaseLoader,
) -> None:
    """`sameObjectAs` is the one-object-per-PK rule, not a second row comparison.

    The damage moves BOTH the second find's expectRows and the row it is handed to
    a different account, so its own row comparison still passes and only the
    identity claim against step 0 refuses it.
    """
    case = damaged_case(_ONE_OBJECT_TWO_FINDS)
    _steps(case)[1]["expectRows"] = [{"id": 3, "owner": "Linus", "balance": 10.00, "version": 1}]
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_LINUS, [_account(3, "Linus", "10.00", 1)]])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match="primary-key identities differ"):
        reads.assert_step(1, reader)


def test_a_step_whose_rows_do_not_carry_the_identity_column_is_refused(
    damaged_case: CaseLoader,
) -> None:
    case = damaged_case(_ONE_OBJECT_TWO_FINDS)
    _steps(case)[1]["identityAttr"] = "account_number"
    reads = ScenarioReads(case)
    reader = ScriptedReads(results=[_LINUS, _LINUS])
    reads.assert_step(0, reader)

    with pytest.raises(CaseFailure, match="do not carry the identity column"):
        reads.assert_step(1, reader)


# --- a query-backed list's first access ---------------------------------------


def test_a_first_access_resolves_the_constructors_object_query_from_the_case(
    corpus_case: CaseLoader,
) -> None:
    """The construction step is never asserted, and its query is still reachable.

    Step 0 built the list and published nothing; step 1's ``on`` names it, and the
    read it resolves is that step's own authored Object Query — read out of the
    accepted case rather than handed across the seam as an unresolved value.
    """
    reads = ScenarioReads(corpus_case(_CONSTRUCTION))
    reader = ScriptedReads(results=[_ORDERS])

    reads.assert_step(1, reader)

    assert len(reader.calls) == 1


def test_a_first_access_decodes_with_the_constructed_lists_own_entity(
    corpus_case: CaseLoader,
) -> None:
    """A value-object-bearing list decodes its document with the SOURCE's schema.

    The rows are Depot rows, so the flat ``address`` document projects through
    Depot's own composite — resolving the entity from the constructor the access
    names, never from the Scenario root.
    """
    depots = [
        {
            "id": 200,
            "customer_id": 1,
            "label": "Dock",
            "__parallax_document_presence_3": True,
            "address": {"line": "1 Dock St", "postcode": "0193"},
        },
        {
            "id": 201,
            "customer_id": 1,
            "label": "Yard",
            "__parallax_document_presence_3": False,
            "address": None,
        },
    ]
    reads = ScenarioReads(corpus_case(_VALUE_OBJECT_LIST))
    reader = ScriptedReads(results=[depots])

    reads.assert_step(1, reader)
    resolved = list(reader.calls)
    reads.assert_step(2, reader)

    assert reader.calls == resolved


# --- the streamed placement ---------------------------------------------------


def test_a_streamed_step_delivers_its_pages_and_publishes_every_root(
    corpus_case: CaseLoader,
) -> None:
    """Its `expectRows` are all three roots, across both pages, in delivery order."""
    reads = ScenarioReads(corpus_case(_STREAMED_EVIDENCE))
    reader = ScriptedReads(results=[*_FIRST_DELIVERY])

    reads.assert_step(0, reader)

    assert len(reader.calls) == 3


def test_two_deliveries_of_one_scenario_each_observe_their_own_state(
    corpus_case: CaseLoader,
) -> None:
    """The write between them is orchestration's; each delivery still grades itself."""
    reads = ScenarioReads(corpus_case(_STREAMED_EVIDENCE))

    reads.assert_step(0, ScriptedReads(results=[*_FIRST_DELIVERY]))
    reads.assert_step(2, ScriptedReads(results=[*_SECOND_DELIVERY]))


def test_a_streamed_step_page_seeking_from_the_wrong_root_is_refused(
    damaged_case: CaseLoader,
) -> None:
    """A step's pages reach the delivery oracle, not a single-statement find path."""
    case = damaged_case(_STREAMED_EVIDENCE)
    _steps(case)[0]["statements"][1]["binds"][0] = 1
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match="Continuation Order coordinate"):
        reads.assert_step(0, ScriptedReads(results=[*_FIRST_DELIVERY]))


def test_a_streamed_step_ending_on_a_full_page_is_refused(damaged_case: CaseLoader) -> None:
    """Dropping the short final page leaves a delivery that never proved exhaustion.

    A grader taking the step's FIRST statement and stopping would accept this: the
    remaining page still returns the two roots page 1 asked for.
    """
    case = damaged_case(_STREAMED_EVIDENCE)
    del _steps(case)[0]["statements"][1]
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match="the delivery is not exhausted"):
        reads.assert_step(0, ScriptedReads(results=[_FIRST_DELIVERY[0]]))


def test_a_streamed_steps_roots_stated_out_of_delivery_order_are_refused(
    damaged_case: CaseLoader,
) -> None:
    """A streamed step's `expectRows` is the one row oracle compared positionally.

    The damage swaps the first and last root and nothing else: the multiset is
    unchanged, both pages still ask for the same size, and the second page still
    seeks from the same coordinate — so every other oracle the step carries still
    passes, and only a positional comparison refuses it.
    """
    case = damaged_case(_STREAMED_EVIDENCE)
    rows = _steps(case)[0]["expectRows"]
    rows[0], rows[-1] = rows[-1], rows[0]
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match=r"scenario\[0\] rows != expectRows"):
        reads.assert_step(0, ScriptedReads(results=[*_FIRST_DELIVERY]))


def test_a_streamed_steps_page_drift_names_the_list_the_step_authored(
    damaged_case: CaseLoader,
) -> None:
    """A Scenario page's drift points at the step's statements, not `then.statements`.

    A read case has a ``then.statements`` to name and a Scenario step has its own
    list, so a diagnostic naming the wrong one sends a case author to a member the
    case does not carry.
    """
    case = damaged_case(_STREAMED_EVIDENCE)
    sql = _steps(case)[0]["statements"][1]["sql"]
    for dialect, text in sql.items():
        sql[dialect] = text.replace("t0.id > ?", "t0.id >= ?")
    reads = ScenarioReads(case)

    with pytest.raises(CaseFailure, match=r"scenario\[0\].statements \(postgres\) page 2 seeks"):
        reads.assert_step(0, ScriptedReads(results=[*_FIRST_DELIVERY]))


# --- what a retained observation outlives -------------------------------------


class _ClosedSession:
    """A held session that answers until it is closed, then refuses like a driver.

    The shape a `uow` group's session presents to a read: two members while it is
    open, and a raise on any use after the transaction ended.
    """

    dialect = "postgres"

    def __init__(self, results: list[list[dict[str, Any]]]) -> None:
        self._reads = ScriptedReads(results=results)
        self._closed = False

    def query(self, sql: str, binds: Any = ()) -> list[dict[str, Any]]:
        if self._closed:
            raise RuntimeError("the session that produced this observation has closed")
        return self._reads.query(sql, binds)

    def close(self) -> None:
        self._closed = True

    @property
    def calls(self) -> list[tuple[str, tuple[Any, ...]]]:
        return self._reads.calls


def test_a_retained_observation_outlives_the_session_that_produced_it(
    corpus_case: CaseLoader,
) -> None:
    """A later access carries no reader of its own, so it cannot need the old one.

    An observation holds the rows, the entity, and the per-hop buckets themselves,
    so the group's held session may commit and close before the step that
    navigates what it fetched.
    """
    reads = ScenarioReads(corpus_case(_EDIT_KEEPS_ITEMS))
    session = _ClosedSession([_ORDER_ONE, _ORDER_ONE_ITEMS])
    reads.assert_step(0, session)
    session.close()

    reads.assert_step(2, ScriptedReads())


def test_a_reuse_after_its_session_closed_needs_no_reader_at_all(
    corpus_case: CaseLoader,
) -> None:
    reads = ScenarioReads(corpus_case(_CONSTRUCTION))
    session = _ClosedSession([_ORDERS])
    reads.assert_step(1, session)
    session.close()

    reads.assert_step(2, ScriptedReads())


# --- driver failures are not semantic failures --------------------------------


def test_a_driver_exception_from_a_step_propagates_unchanged(corpus_case: CaseLoader) -> None:
    boom = RuntimeError("connection reset by peer")
    reads = ScenarioReads(corpus_case(_POPULATED_LIST))

    with pytest.raises(RuntimeError, match="connection reset by peer"):
        reads.assert_step(0, ScriptedReads(results=[boom]))
