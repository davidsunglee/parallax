"""API-suite stories against real Postgres (m-api-conformance, spec §"API
Conformance Suite").

Every registered story — write (`parallax.conformance.stories`) or graph-read
(`parallax.conformance.graph_stories`); the same executable functions the Usage
Guide renders — executes here through the **shipped** surface:
`parallax.snapshot.connect` over the `parallax-postgres` adapter against the
real Testcontainers Postgres, inside the documented API-conformance lane
(python.md: pytest ``-m api_conformance`` under ``tests/api_conformance/``,
"executing idiomatic public-API code through the shipped `parallax-snapshot`
extension and `parallax-postgres` adapter"; IMPLEMENTING.md "Continuous API
Conformance Lane" step 2). Docker-backed: the shared ``provisioner`` fixture
skips with a recorded reason when Docker is unavailable (never silently), and
the ``python-database`` CI job fails on any skip. A write story's grading is
the mirrored case's own oracle: a story returning rows must observe its final
find's `expectRows`; a writeSequence story must leave exactly `then.tableState`
behind. The one `kind == "boundary"` story (`m-unit-work-004`) is EXCLUDED from
this file's own grading loop (COR-3 Phase 8 increment 6, DQ5): the D-17
case-driven boundary runner (`test_boundary_run.py`) grades it — and every
other boundary-shape case — directly against the corpus now, so the story
function survives registered only for the Usage Guide and the fake-port wire
pin (`test_write_no_drift.py`). A graph story's grading is bespoke per case
(see the section below).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast

import pytest

from conftest import (
    case_document,
    case_fixtures,
    compare_binds,
    compare_graph,
    compare_rows,
    instance_row,
)
from parallax.conformance import animal_owner, case_format, engine
from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_stories import (
    GRAPH_STORIES,
    history_of_a_concrete_temporal_node_distinguishes_milestones,
)
from parallax.conformance.read_models import Cat, Dog
from parallax.conformance.read_stories import READ_STORIES, ReadStory
from parallax.conformance.stories import WRITE_STORIES, WriteStory
from parallax.conformance.vo_models import CUSTOMER_REGISTRY
from parallax.core import LATEST, edge_of, is_loaded, narrowed, pin_of
from parallax.core.descriptor import Metamodel
from parallax.core.dialect import POSTGRES
from parallax.core.entity.base import EntityRegistry
from parallax.core.entity.expressions import UnloadedRelationshipError
from parallax.core.entity.value_object import to_document
from parallax.snapshot import connect

pytestmark = pytest.mark.api_conformance

_CASES = {c.case_id: c for c in case_format.load_cases()}


def _final_find_expect_rows(case_id: str) -> list[dict[str, Any]]:
    """The last scenario find step's ``expectRows`` — the story's returned oracle."""
    steps = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["when"]["scenario"])
    finds = [step for step in steps if "find" in step]
    assert finds, case_id
    return cast("list[dict[str, Any]]", finds[-1]["expectRows"])


def _reset_for(case_id: str, provisioner: Any) -> Any:
    case = _CASES[case_id]
    meta = engine.load_case_metamodel(case)
    provisioner.reset(meta, case_fixtures(case))
    return meta


def _reset_for_registry(case_id: str, provisioner: Any, registry: EntityRegistry) -> Metamodel:
    """Like :func:`_reset_for`, but provisions from ``registry``'s OWN
    :meth:`~parallax.core.entity.base.EntityRegistry.metamodel` rather than
    the ingested corpus descriptor (ledger D-20): needed whenever `db.find`'s
    wrap must resolve through a registry OTHER than the process default (the
    animal family's REAL owner, scoped to
    `animal_owner.ANIMAL_OWNER_REGISTRY`) — structurally equivalent to the
    ingested descriptor (proven by the descriptor no-drift guard), so
    provisioning from it is exactly as sound."""
    case = _CASES[case_id]
    meta = registry.metamodel()
    provisioner.reset(meta, case_fixtures(case))
    return meta


# `kind == "boundary"` (m-unit-work-004) is EXCLUDED from execution here (COR-3
# Phase 8 increment 6, DQ5): the D-17 case-driven boundary runner
# (`tests/api_conformance/test_boundary_run.py`) now grades it directly
# against the corpus, case-driven like every other boundary case — the hand
# story's function stays registered (`stories.WRITE_STORIES`) ONLY so the
# Usage Guide keeps rendering it (`api_suite.EXAMPLES`) and the fake-port
# wire pin (`test_write_no_drift.test_boundary_story_withholds_the_callback_
# value`) keeps proving its own DML shape — this hand-mirrored REAL-DATABASE
# grading is what retires.
_EXECUTED_STORIES = [story for story in WRITE_STORIES if story.kind != "boundary"]
_STORY_IDS = [story.case_id for story in _EXECUTED_STORIES]


@pytest.mark.parametrize("story", _EXECUTED_STORIES, ids=_STORY_IDS)
def test_story_runs_through_the_shipped_surface(story: WriteStory, provisioner: Any) -> None:
    # D-33: a story compiled under its OWN `registry` (the Customer/Location/
    # Depot mirror's `CUSTOMER_REGISTRY`, ledger D-20) provisions/connects
    # through THAT registry's own metamodel, the SAME `_reset_for_registry`
    # scoping the graph stories below already use — never the bare ingested
    # corpus descriptor `_reset_for` resolves every other story through.
    meta = (
        _reset_for_registry(story.case_id, provisioner, story.registry)
        if story.registry is not None
        else _reset_for(story.case_id, provisioner)
    )
    # D-29: a story's own scripted-clock FACTORY (never a shared instance) —
    # this consumer's fresh clock, independent of `test_write_no_drift.py`'s.
    clock = story.clock() if story.clock is not None else None
    db = connect(provisioner.port, meta, clock=clock)

    result = story.run(db)
    if result is not None:
        # Commit and abort stories both conclude with an observing find; its
        # rows must equal the mirrored case's final `expectRows` (D-23,
        # instance-native grading: a scenario's own `expectRows` is
        # INSTANCE-form, m-case-format — physical-column-keyed, `instance_row`,
        # never the canonical camelCase `engine.wire_row` used to render).
        compare_rows([instance_row(row) for row in result], _final_find_expect_rows(story.case_id))
        return

    # A writeSequence story observes no rows; the committed table state must
    # equal the case's `then.tableState`, table for table.
    expected_state = cast(
        "dict[str, list[dict[str, Any]]]",
        case_document(_CASES[story.case_id])["then"]["tableState"],
    )
    observed_state = engine.read_table_state(provisioner.port, meta, POSTGRES)
    assert set(observed_state) >= set(expected_state), (story.case_id, observed_state)
    for table, expected_rows in expected_state.items():
        compare_rows(observed_state[table], expected_rows)


# --------------------------------------------------------------------------- #
# Graph stories (m-snapshot-read / m-navigate, COR-3 Phase 7 increment 6b):    #
# the read-side sibling of the write stories above, executed through the SAME #
# shipped `parallax.snapshot.connect` + `parallax-postgres` surface. Grading  #
# is bespoke per story (unlike the write stories' shared row/table-state      #
# comparators): each assertion mirrors its case's own `then.graph`/           #
# `identityChecks`/scenario oracle as closely as one in-process assertion     #
# can — the developer-facing guarantees a wire grade cannot see (reference    #
# identity surviving the frozen-node wrap, `is_loaded` /                      #
# `UnloadedRelationshipError`, `pin_of`/`edge_of` on a materialized node).     #
# --------------------------------------------------------------------------- #
_GRAPH_STORIES_BY_ID = {story.case_id: story for story in GRAPH_STORIES}


def test_diamond_identity_shares_one_child_node(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-001"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # The diamond: both include paths reach OrderItem 12 then OrderItem 11 (id
    # desc / shipped_on asc happen to agree here) — one materialized node, not
    # two lookalike copies, exactly the reference identity `then.identityChecks`
    # would grade at the wire level for the graph half of this case.
    assert order.items[0] is order.items_by_ship_date[0]
    assert order.items[1] is order.items_by_ship_date[1]
    assert snapshot.execution.round_trips == 3


def test_back_reference_cycle_resolves_to_the_root(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-011"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    # `then.identityChecks` graded as Python reference identity: the back-
    # reference IS the root node, never a lookalike re-fetch.
    assert order.items[0].order is order
    assert order.items[1].order is order
    assert snapshot.execution.round_trips == 2


def test_closed_world_unloaded_access_raises_without_sql(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-009"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert is_loaded(order, "statuses") is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        order.statuses  # noqa: B018 - the access itself is the assertion
    # The access issues no SQL of its own: the materializing find is the only
    # round trip on record (m-snapshot-read-009 is this suite's official grader
    # for the closed-world absence witness, `lane: api-conformance`).
    assert snapshot.execution.round_trips == 1


def test_empty_root_materializes_no_children(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-004"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    assert snapshot.results() == []
    assert snapshot.execution.round_trips == 1


def test_empty_intermediate_level_short_circuits(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-005"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    order = snapshot.result()
    assert order.items == ()
    assert snapshot.execution.round_trips == 2


def test_pinned_graph_at_a_past_business_instant(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-navigate-013"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    policy = next(p for p in snapshot.results() if p.id == 1)
    coverage = policy.coverages[0]
    assert coverage.amount == Decimal("600.00")  # the HEAD as of 2024-03-01, not the current 700
    edge = edge_of(coverage)
    assert edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge.transaction_time == dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
    pin = snapshot.pin
    assert pin.valid_time == dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
    assert pin.transaction_time is LATEST


def test_mutation_has_no_writeback(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-010"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    mutated, reread = story.run(db)
    assert mutated.name == "Mutant"  # the in-memory copy sees the edit
    assert reread.result().name == "Ada"  # the re-read never observes it


def test_history_of_a_concrete_temporal_node_distinguishes_milestones(provisioner: Any) -> None:
    # SUPPLEMENTAL (Spec-2 remediation) — NOT tied to any case's exercised
    # status: `m-inheritance-100`'s own point read is graded by its `ReadStory`
    # below (`test_read_story_runs_through_the_shipped_surface`), through the
    # generic case-driven runner, exactly like every other read story. This
    # proves the SEPARATE milestone-HISTORY shape over the SAME fixture: a
    # concrete TPCS node (DepositRate) whose family's as-of axes are declared
    # on the root (Rate) alone still gets its own pin/edge attached, and a
    # `.history(...)` milestone-set read's closed historical correction and
    # current row remain distinct identities sharing one business key.
    meta = _reset_for("m-inheritance-100", provisioner)
    db = connect(provisioner.port, meta)
    snapshot = history_of_a_concrete_temporal_node_distinguishes_milestones(db)
    nodes = snapshot.results()
    assert len(nodes) == 2
    by_amount = {node.amount: node for node in nodes}
    historical = by_amount[Decimal("2.25")]
    current = by_amount[Decimal("2.50")]
    assert historical is not current  # distinct identities per milestone
    assert historical.grade == "B"
    assert current.grade == "A"
    historical_edge = edge_of(historical)
    current_edge = edge_of(current)
    assert historical_edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert historical_edge.transaction_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert current_edge.transaction_time == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    # Both `pin_of` calls succeed (the root-owned axes attach a pin to a
    # concrete node exactly as they would at the abstract root or an
    # abstract-subtype position).
    pin_of(historical)
    pin_of(current)


def test_one_to_one_peer_attaches_as_a_single_object(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-007"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_id = {person.id: person for person in snapshot.results()}
    assert by_id[1].passport is not None
    assert by_id[1].passport.number == "P-AAA"
    assert by_id[2].passport is not None
    assert by_id[2].passport.number == "P-BBB"
    assert by_id[3].passport is None  # no passport on record -> a null peer
    assert snapshot.execution.round_trips == 2


def test_animal_owner_reaches_root_and_narrowed_subtype_view(provisioner: Any) -> None:
    # The animal family's REAL owner (ledger D-20): provisioned from its OWN
    # scoped registry, never the ingested descriptor (`_reset_for_registry`).
    story = _GRAPH_STORIES_BY_ID["m-snapshot-read-012"]
    meta = _reset_for_registry(story.case_id, provisioner, animal_owner.ANIMAL_OWNER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    alice = snapshot.result()
    assert isinstance(alice, AnimalOwnerPerson)
    assert alice.name == "Alice"
    assert {pet.name for pet in alice.animals} == {"Rex", "Whiskers"}
    dogs = narrowed(alice, AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", dogs)] == ["Rex"]
    assert snapshot.execution.round_trips == 3


def test_narrowed_pets_view_populates_per_owner(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-065"]
    meta = _reset_for_registry(story.case_id, provisioner, animal_owner.ANIMAL_OWNER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {person.name: person for person in snapshot.results()}
    alice_dogs = narrowed(by_name["Alice"], AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", alice_dogs)] == ["Rex"]
    bob_dogs = narrowed(by_name["Bob"], AnimalOwnerPerson.pets.narrow(Dog))
    assert [dog.name for dog in cast("tuple[Any, ...]", bob_dogs)] == ["Fido"]
    carol_dogs = narrowed(by_name["Carol"], AnimalOwnerPerson.pets.narrow(Dog))
    assert carol_dogs == ()
    assert snapshot.execution.round_trips == 2


def test_equivalent_narrow_spellings_dedupe_to_one_view(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-066"]
    meta = _reset_for_registry(story.case_id, provisioner, animal_owner.ANIMAL_OWNER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    by_name = {person.name: person for person in snapshot.results()}
    alice_view = narrowed(by_name["Alice"], AnimalOwnerPerson.pets.narrow(Cat, Dog))
    assert {pet.name for pet in cast("tuple[Any, ...]", alice_view)} == {"Rex", "Whiskers"}
    assert snapshot.execution.round_trips == 2


def test_distinct_narrowed_views_populate_independently(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-067"]
    meta = _reset_for_registry(story.case_id, provisioner, animal_owner.ANIMAL_OWNER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    alice = next(person for person in snapshot.results() if person.name == "Alice")
    alice_dogs = narrowed(alice, AnimalOwnerPerson.pets.narrow(Dog))
    alice_cats = narrowed(alice, AnimalOwnerPerson.pets.narrow(Cat))
    assert [pet.name for pet in cast("tuple[Any, ...]", alice_dogs)] == ["Rex"]
    assert [pet.name for pet in cast("tuple[Any, ...]", alice_cats)] == ["Whiskers"]
    assert snapshot.execution.round_trips == 3


def _vo_owner_row(instance: Any, vo_py_name: str = "address") -> dict[str, Any]:
    """A materialized VO-bearing owner's own row, PHYSICAL-column-keyed
    (``instance_row``), with its value-object member serialized to its
    canonical document (``to_document``) so ``compare_graph`` can recurse
    into it exactly like the wire-level engine's own `then.graph` grading."""
    row = instance_row(instance)
    row[vo_py_name] = to_document(getattr(instance, vo_py_name))
    return row


def _assert_vo_owner_graph(case_id: str, snapshot: Any, entity_name: str, pk_column: str) -> None:
    expected_by_pk = {
        row[pk_column]: row
        for row in cast(
            "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"][entity_name]
        )
    }
    observed = snapshot.results()
    assert {instance.id for instance in observed} == set(expected_by_pk)
    for instance in observed:
        compare_graph(_vo_owner_row(instance), expected_by_pk[instance.id])


def test_transaction_time_only_vo_owner_as_of_latest(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-028"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Supplier", "sup_id")
    assert snapshot.execution.round_trips == 1


def test_transaction_time_only_vo_owner_as_of_a_past_instant(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-029"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Supplier", "sup_id")
    assert snapshot.execution.round_trips == 1


def test_bitemporal_vo_owner_as_of_latest(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-030"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Branch", "br_id")
    assert snapshot.execution.round_trips == 1


def test_bitemporal_vo_owner_as_of_a_past_audit_point(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-value-object-031"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Branch", "br_id")
    assert snapshot.execution.round_trips == 1


def _assert_typed_per_variant_graph(case_id: str, snapshot: Any, entity_name: str) -> None:
    """ledger D-22: each materialized instance renders to its OWN concrete
    class's declared members plus ``familyVariant`` (`instance_row`,
    physical-column-keyed, spec §4 "observable as `type(node)`") — never a
    sibling's null-padded column, matching the case's own per-variant
    `then.graph` exactly (order-insensitive, `compare_rows`)."""
    expected = cast(
        "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"][entity_name]
    )
    observed = [instance_row(instance, family_variant=True) for instance in snapshot.results()]
    compare_rows(observed, expected)


def test_tph_abstract_root_read_materializes_typed_per_variant_instances(provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-106"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Payment")
    assert snapshot.execution.round_trips == 1


def test_tph_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-107"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Animal")
    assert snapshot.execution.round_trips == 1


def test_tph_or_across_branches_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-108"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Animal")
    assert snapshot.execution.round_trips == 1


def test_tpcs_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-inheritance-109"]
    meta = _reset_for(story.case_id, provisioner)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_typed_per_variant_graph(story.case_id, snapshot, "Document")
    assert snapshot.execution.round_trips == 1


def _assert_customer_predicate_rows(case_id: str, snapshot: Any) -> None:
    """The row-form predicate original's own ``then.rows`` oracle — id/name
    only, never the exact SQL the corpus's row-form classification would
    otherwise demand (`graph_stories`'s own module docstring explains why
    this grades here, bespoke, rather than through ``ReadStory``'s
    byte-exact generic runner)."""
    expected = cast("list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["rows"])
    observed = [{"id": customer.id, "name": customer.name} for customer in snapshot.results()]
    compare_rows(observed, expected)


# The seven Customer nested-predicate stories share ONE execution shape
# (reset, run, `then.rows`, one round trip), so a single parametrized runner
# drives them — the READ-story generic-runner precedent below — with the
# behavior each case witnesses preserved as the parameter id.
@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("m-value-object-001", id="nested-eq-city-selects-matching-owners"),
        pytest.param("m-value-object-002", id="deep-nested-eq-country-selects-the-matching-owner"),
        pytest.param("m-value-object-007", id="nested-is-null-collapses-every-not-present-state"),
        pytest.param("m-value-object-015", id="to-many-nested-exists-is-a-nonempty-test"),
        pytest.param(
            "m-value-object-016", id="to-many-nested-not-exists-folds-every-not-present-state"
        ),
        pytest.param("m-value-object-017", id="to-many-any-element-eq-matches-some-element"),
        pytest.param(
            "m-value-object-019", id="to-many-scoped-exists-requires-one-element-to-satisfy-both"
        ),
    ],
)
def test_customer_nested_predicate_story_selects_the_golden_owners(
    case_id: str, provisioner: Any
) -> None:
    story = _GRAPH_STORIES_BY_ID[case_id]
    meta = _reset_for_registry(story.case_id, provisioner, CUSTOMER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_customer_predicate_rows(story.case_id, snapshot)
    assert snapshot.execution.round_trips == 1


@pytest.mark.parametrize(
    "case_id",
    [
        pytest.param("m-value-object-023", id="whole-nested-composite"),
        pytest.param("m-value-object-024", id="composite-under-a-filter"),
    ],
)
def test_customer_owner_materializes_its_composite(case_id: str, provisioner: Any) -> None:
    story = _GRAPH_STORIES_BY_ID[case_id]
    meta = _reset_for_registry(story.case_id, provisioner, CUSTOMER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_vo_owner_graph(story.case_id, snapshot, "Customer", "id")
    assert snapshot.execution.round_trips == 1


def _assert_customer_locations_graph(case_id: str, snapshot: Any) -> None:
    expected_by_id = {
        row["id"]: row
        for row in cast(
            "list[dict[str, Any]]", case_document(_CASES[case_id])["then"]["graph"]["Customer"]
        )
    }
    observed = snapshot.results()
    assert {customer.id for customer in observed} == set(expected_by_id)
    for customer in observed:
        row = _vo_owner_row(customer)
        row["locations"] = [_vo_owner_row(location) for location in customer.locations]
        compare_graph(row, expected_by_id[customer.id])


def test_customer_locations_deep_fetch_materializes_the_child_document_too(
    provisioner: Any,
) -> None:
    story = _GRAPH_STORIES_BY_ID["m-deep-fetch-018"]
    meta = _reset_for_registry(story.case_id, provisioner, CUSTOMER_REGISTRY)
    db = connect(provisioner.port, meta)
    snapshot = story.run(db)
    _assert_customer_locations_graph(story.case_id, snapshot)
    assert snapshot.execution.round_trips == 2


def test_every_graph_story_mirrors_an_active_case_exactly_once() -> None:
    assert len(_GRAPH_STORIES_BY_ID) == len(GRAPH_STORIES)
    for story in GRAPH_STORIES:
        assert story.case_id in _CASES, story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id


# --------------------------------------------------------------------------- #
# Read stories (m-api-conformance S1 remediation): a GENERIC runner, unlike    #
# the write/graph stories above — every read-only example's execution shape   #
# is identical (reset, `db.find(build())`, compare), so ONE parametrized test #
# drives every `read_stories.READ_STORIES` entry instead of a hand-rolled     #
# per-case function. Grading is the case's own `then.rows` (order-insensitive,#
# exact-typed, physical-column-keyed — `instance_row`, never the canonical    #
# camelCase `orderedOn` spelling `then.rows` never uses) plus `then.roundTrips`#
# when the case declares it. `familyVariant` is reported only for a case whose #
# own oracle rows declare it (an abstract-root inheritance read) — the        #
# API-suite's own polymorphism observation (`python.md` §4: "observable as    #
# `type(node)`"), not a field the developer surface itself exposes.           #
#                                                                              #
# `story.concurrency` (COR-3 Phase 8 increment 6, the `m-read-lock` matrix)   #
# opts a story into the TRANSACTIONAL half instead: `tx.find(build())` inside #
# a `db.transact` of the declared participation mode, still graded against    #
# the SAME `then.rows` oracle, PLUS the statements this story's own find      #
# ACTUALLY executed (review remediation finding 3, `_StatementCapturePort`    #
# below) — the runtime proof that the mode actually drives whether the        #
# emitted SQL carries the shared read-lock suffix (unobservable from          #
# `then.rows` alone: two stories can return identical rows while one holds a  #
# lock and the other does not).                                               #
# --------------------------------------------------------------------------- #
_READ_STORY_IDS = [story.case_id for story in READ_STORIES]


class _StatementCapturePort:
    """A pass-through ``m-db-port`` decorator capturing every SQL statement +
    binds a read story's find ACTUALLY executes — the SAME port-seam capture
    point ``test_run_sweep._ReadCapturePort`` establishes, generalized to
    record the statement text (not just its rows): `then.rows` alone cannot
    distinguish whether a `m-read-lock` story's runtime DEVELOPER path
    emitted the shared read-lock suffix, only the statement text can (review
    remediation finding 3). ``transaction`` nests another capture wrapper
    sharing this SAME ``statements`` list (mirroring ``_ReadCapturePort``'s
    own ``transaction``), so a `tx.find` inside `db.transact` is captured
    from the SAME single execution as a non-transactional `db.find`.
    """

    def __init__(
        self, inner: Any, statements: list[tuple[str, tuple[object, ...]]] | None = None
    ) -> None:
        self._inner = inner
        self.statements: list[tuple[str, tuple[object, ...]]] = (
            statements if statements is not None else []
        )

    def execute(self, sql: str, binds: Any) -> list[dict[str, Any]]:
        self.statements.append((sql, tuple(binds)))
        return self._inner.execute(sql, binds)

    def execute_write(self, sql: str, binds: Any) -> int:
        return self._inner.execute_write(sql, binds)

    def transaction(self, body: Any) -> Any:
        statements = self.statements

        def wrapped(conn: Any) -> Any:
            return body(_StatementCapturePort(conn, statements=statements))

        return self._inner.transaction(wrapped)


@pytest.mark.parametrize("story", READ_STORIES, ids=_READ_STORY_IDS)
def test_read_story_runs_through_the_shipped_surface(story: ReadStory, provisioner: Any) -> None:
    meta = _reset_for(story.case_id, provisioner)
    port = _StatementCapturePort(provisioner.port)
    db = connect(port, meta)
    if story.concurrency is not None:
        snapshot = db.transact(lambda tx: tx.find(story.build()), concurrency=story.concurrency)
    else:
        snapshot = db.find(story.build())
    then = cast("dict[str, Any]", case_document(_CASES[story.case_id])["then"])
    expected_rows = cast("list[dict[str, Any]]", then["rows"])
    expects_variant = any("familyVariant" in row for row in expected_rows)
    observed_rows = [
        instance_row(instance, family_variant=expects_variant) for instance in snapshot.results()
    ]
    compare_rows(observed_rows, expected_rows)
    expected_round_trips = then.get("roundTrips")
    if expected_round_trips is not None:
        assert snapshot.execution.round_trips == expected_round_trips, story.case_id

    # Review remediation finding 3: grade the statements this story's find
    # ACTUALLY executed against the case's own authored golden (postgres
    # dialect) — asserting the `for share of t0` lock suffix's presence
    # (`m-read-lock-002`) or absence (`-003`/`-005`/every other read story)
    # exactly as authored, reusing the SAME driver-SQL translation and
    # exact-Decimal bind comparison every other run lane uses rather than an
    # ad hoc string match.
    golden_statements = then.get("statements")
    assert golden_statements is not None, story.case_id
    golden_statements = cast("list[dict[str, Any]]", golden_statements)
    assert len(port.statements) == len(golden_statements), (story.case_id, port.statements)
    for (sql, binds), entry in zip(port.statements, golden_statements, strict=True):
        golden_sql = entry["sql"]
        golden_text = (
            cast("dict[str, str]", golden_sql)["postgres"]
            if isinstance(golden_sql, dict)
            else golden_sql
        )
        assert sql == POSTGRES.to_driver_sql(cast("str", golden_text)), story.case_id
        compare_binds(binds, cast("list[object]", entry.get("binds", [])))


def test_every_read_story_mirrors_an_active_case_exactly_once() -> None:
    by_id = {story.case_id: story for story in READ_STORIES}
    assert len(by_id) == len(READ_STORIES)
    for story in READ_STORIES:
        assert story.case_id in _CASES, story.case_id
        assert _CASES[story.case_id].shape == "read", story.case_id
        model_ref = str(case_document(_CASES[story.case_id])["model"])
        assert story.model == model_ref.removeprefix("models/").removesuffix(".yaml"), story.case_id
