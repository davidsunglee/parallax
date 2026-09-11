"""The snapshot action-step lane, driven database-free: the `mutate` action's
edited copy and how its assignments are judged, the `access` step's graph
observation off the retained view, the `expectError` and `expectGraph`
grading, the `write:` step the lane commits as its own unit of work, and the
lane's own refusals, each named for the case.

The lane is driven through its own entry points here, the way the façade
dispatches a scenario carrying an action step to them.
"""

from __future__ import annotations

import copy
import dataclasses
import datetime as dt
import decimal
import functools
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pytest

from parallax.conformance import case_format, models, sweep
from parallax.conformance._database_control import CaseDatabase
from parallax.conformance._lanes import snapshot
from parallax.conformance._lifecycle_observation import lifecycle_run
from parallax.conformance._mechanism import case_document, model_facts
from parallax.conformance._mechanism.envelope import Emission, EngineError, ScenarioRun
from parallax.core._formation_profile import form_metamodel
from parallax.core.base import (
    INFINITY,
    STRING,
)
from parallax.core.db_port import (
    DatabaseConnection,
    Row,
    TransactionOutcome,
)
from parallax.core.metamodel import (
    AbstractRoot,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    Table,
    TablePerHierarchy,
    ValueObjectAttributeDeclaration,
    ValueObjectOccurrenceDeclaration,
    ValueObjectShapeDeclaration,
    ValueObjectShapeKey,
)
from parallax.core.temporal_read import Pin
from tests._support.db_port import body_outcome
from tests.unit._metamodel_support import Declaration, attribute, key, source
from tests.unit.conformance._recording_ports import FakeDbPort, FakeWritePort, QueueDbPort


# One corpus read serves the whole module, and both indexes project it: what
# they answer is shared between tests, so a test that edits a document deep-copies
# it first.
@functools.cache
def _corpus() -> tuple[case_format.Case, ...]:
    return tuple(case_format.load_cases())


def _by_id(cases: Sequence[case_format.Case]) -> Mapping[str, case_format.Case]:
    # A case id is unique within its module, so a collision here means two case
    # files claim one id; keying them into a dict would silently resolve every
    # lookup to whichever file sorts last.
    index: dict[str, case_format.Case] = {}
    for case in cases:
        claimed = index.setdefault(case.case_id, case)
        if claimed is not case:
            raise ValueError(
                f"case id {case.case_id!r} is claimed by both "
                f"{claimed.path.name} and {case.path.name}"
            )
    return index


@functools.cache
def _reachable_by_id() -> Mapping[str, case_format.Case]:
    return _by_id(sweep.reachable_cases(cases=list(_corpus())))


def _case(case_id: str) -> case_format.Case:
    return _reachable_by_id()[case_id]


def _synthetic_write(shape: str, document: dict[str, object]) -> case_format.Case:
    document.setdefault("model", "models/account.yaml")
    return case_format.Case(
        path=Path("m-unit-work-999-synthetic.yaml"),
        case_id="m-unit-work-999",
        shape=shape,
        tags=("m-unit-work", "slice-snapshot-1"),
        model="models/account.yaml",
        document=document,
    )


def _compile(case: case_format.Case, dialect_name: str) -> tuple[list[Emission], int]:
    return snapshot.compile_scenario(case, dialect_name, case_document.scenario_steps(case))


def _run(case: case_format.Case, port: CaseDatabase) -> ScenarioRun:
    return snapshot.run_scenario(
        case, port, case_document.scenario_steps(case), lifecycle_run(None)
    )


# --------------------------------------------------------------------------- #
# The scenario `mutate` action over a snapshot graph: the edited copy a step    #
# publishes and how its assignments are judged. What a root LOOKS like is the  #
# wire materializer's own contract (`test_wire_reads.py`).                      #
# --------------------------------------------------------------------------- #
_VARIANT_ROOT = EntityIdentity("catalog", "AssetRecord")
_NAMED_VARIANT = EntityIdentity("catalog", "NamedVariant")
_FIRST_SHARED_VARIANT = EntityIdentity("catalog", "SharedVariant")
_SECOND_SHARED_VARIANT = EntityIdentity("archive", "SharedVariant")
_UNRELATED_NAMED_VARIANT = EntityIdentity("unrelated", "NamedVariant")


def _rendering_value_object(name: str, column: str) -> ValueObjectOccurrenceDeclaration:
    return ValueObjectOccurrenceDeclaration(
        name=name,
        storage=Column(column),
        shape=ValueObjectShapeDeclaration(
            key=ValueObjectShapeKey(),
            attributes=(ValueObjectAttributeDeclaration("label", STRING),),
        ),
    )


_VARIANT_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_VARIANT_ROOT,
            container=Table("asset_record"),
            attributes=(key(_VARIANT_ROOT),),
            value_objects=(_rendering_value_object("mailingAddress", "familyVariant"),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_NAMED_VARIANT,
            value_objects=(_rendering_value_object("namedProfile", "named_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "named"),
        ),
        Declaration(
            identity=_FIRST_SHARED_VARIANT,
            value_objects=(_rendering_value_object("catalogProfile", "catalog_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "catalog-shared"),
        ),
        Declaration(
            identity=_SECOND_SHARED_VARIANT,
            value_objects=(_rendering_value_object("archiveProfile", "archive_profile"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_VARIANT_ROOT), "archive-shared"),
        ),
        Declaration(
            identity=_UNRELATED_NAMED_VARIANT,
            container=Table("unrelated_named_variant"),
            attributes=(key(_UNRELATED_NAMED_VARIANT),),
            value_objects=(_rendering_value_object("wrongProfile", "wrong_profile"),),
        ),
    )
)


_ATTACH_OWNER = EntityIdentity("catalog", "Owner")
_ATTACH_TARGET = EntityIdentity("catalog", "Target")

# One Entity whose Value Object storage column is spelled exactly like a
# relationship it also carries: the two namespaces must not overwrite each other
# on the wire.
_ATTACH_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_ATTACH_OWNER,
            container=Table("owner"),
            attributes=(key(_ATTACH_OWNER), attribute(_ATTACH_OWNER, "targetId")),
            value_objects=(_rendering_value_object("profile", "details"),),
        ),
        Declaration(
            identity=_ATTACH_TARGET,
            container=Table("target"),
            attributes=(key(_ATTACH_TARGET),),
        ),
    )
)


def _scenario_result(
    *roots: dict[str, object], pin: Pin | None = None, identity: EntityIdentity | None = None
) -> Any:
    return snapshot._ScenarioStepResult(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
        roots=tuple(roots), pin=pin, identity=identity
    )


_ORDERS_MODEL = model_facts.load_case_metamodel(_case("m-snapshot-read-010"))
_ORDER_IDENTITY = model_facts.case_entity(_ORDERS_MODEL, "parallax.compatibility.Order").identity


def _edited_copy(step: Mapping[str, object], on: int, source: Any) -> Any:
    return snapshot._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
        _case("m-snapshot-read-010"), _ORDERS_MODEL, step, on, source
    )


def _order_view(**members: object) -> Any:
    return _scenario_result(dict(members), identity=_ORDER_IDENTITY)


def test_edited_copy_raises_when_the_target_step_holds_zero_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    with pytest.raises(EngineError, match="expected exactly one"):
        _edited_copy(step, 0, _scenario_result(identity=_ORDER_IDENTITY))


def test_edited_copy_raises_when_the_target_step_holds_many_nodes() -> None:
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant"}}
    source = _scenario_result(
        {"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}, identity=_ORDER_IDENTITY
    )
    with pytest.raises(EngineError, match="expected exactly one"):
        _edited_copy(step, 0, source)


def test_edited_copy_raises_when_set_is_not_a_mapping() -> None:
    step = {"action": "mutate", "on": 0, "set": "not-a-mapping"}
    with pytest.raises(EngineError, match="`set` is a mapping"):
        _edited_copy(step, 0, _order_view(id=1, name="Ada"))


def test_edited_copy_carries_every_named_member_and_leaves_its_source_alone() -> None:
    # An edit DERIVES: the copy carries the assignment and the node it was
    # derived from still holds what the read materialized, which is the whole
    # difference between an authored edit and an in-place assignment.
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant", "qty": 9}}
    source = _order_view(id=1, name="Ada", qty=5)
    copy = _edited_copy(step, 0, source)
    assert copy.roots[0] == {"id": 1, "name": "Mutant", "qty": 9}
    assert source.roots[0] == {"id": 1, "name": "Ada", "qty": 5}


def test_edited_copy_carries_the_sources_pin_and_identity() -> None:
    # What lets a chain of edits keep answering the pin question the same way,
    # and a later step name the copy exactly as it names the read.
    pin = Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC), valid_time=None)
    source = _scenario_result({"id": 1, "name": "Ada"}, pin=pin, identity=_ORDER_IDENTITY)
    copy = _edited_copy({"action": "mutate", "on": 0, "set": {"name": "Mutant"}}, 0, source)
    assert (copy.pin, copy.identity) == (pin, _ORDER_IDENTITY)


def test_edited_copy_with_no_set_restates_the_sources_own_state() -> None:
    # The change-free edit (`test_edit.py`'s `_BRANCHES` second branch): legal,
    # and a copy rather than the source itself.
    source = _order_view(id=1, name="Ada")
    copy = _edited_copy({"action": "mutate", "on": 0}, 0, source)
    assert copy.roots[0] == {"id": 1, "name": "Ada"}
    assert copy.roots[0] is not source.roots[0]


def test_edited_copy_refuses_a_set_naming_a_relationship_member() -> None:
    # No edit changes a relationship member: a carried view describes what a read
    # observed, so authoring `items` would state a fetch that never happened.
    step: dict[str, object] = {"action": "mutate", "on": 0, "set": {"items": []}}
    source = _order_view(id=1, name="Ada", items=())
    with pytest.raises(EngineError, match="name relationship members"):
        _edited_copy(step, 0, source)


def test_edited_copy_refuses_the_whole_set_when_one_name_is_unassignable() -> None:
    # The assignable name is authored FIRST, so a per-name copy-then-check would
    # carry `name` past the refusal: the whole `set` is rejected and the source
    # still holds the state the find step materialized.
    step = {"action": "mutate", "on": 0, "set": {"name": "Mutant", "nickname": "Nick"}}
    source = _order_view(id=1, name="Ada")
    with pytest.raises(EngineError, match="has no assignable member of"):
        _edited_copy(step, 0, source)
    assert source.roots[0] == {"id": 1, "name": "Ada"}


def test_edited_copy_refuses_an_assignment_to_the_primary_key() -> None:
    # `python.md`'s edit contract: a primary-key target may not be assigned. The
    # engine reaches the SAME verdict the typed `edit(**changes)` does rather
    # than merging whatever the case authored.
    step = {"action": "mutate", "on": 0, "set": {"id": 2}}
    source = _order_view(id=1, name="Ada")
    with pytest.raises(EngineError, match="primary-key fields may not be assigned"):
        _edited_copy(step, 0, source)


def test_edited_copy_refuses_an_ill_typed_assignment() -> None:
    # The other half of the same verdict: a value that does not match the
    # member's declared type is refused at edit time, never carried into a copy
    # a later step names.
    step = {"action": "mutate", "on": 0, "set": {"qty": "five"}}
    source = _order_view(id=1, name="Ada", qty=5)
    with pytest.raises(EngineError, match="does not match the declared type"):
        _edited_copy(step, 0, source)


def test_edited_copy_carries_the_decoded_value_a_member_would_hold() -> None:
    # A case authors canonical Wire literals; the read's own member state holds
    # managed values, so the copy's does too rather than mixing vocabularies.
    step = {"action": "mutate", "on": 0, "set": {"price": "12.75"}}
    copy = _edited_copy(step, 0, _order_view(id=1, price=decimal.Decimal("10.50")))
    assert copy.roots[0]["price"] == decimal.Decimal("12.75")
    assert isinstance(copy.roots[0]["price"], decimal.Decimal)


def test_an_edit_chain_carries_the_sources_relationship_arm_at_every_hop() -> None:
    # What `m-snapshot-read-022`'s access cannot ask on this lane, because it
    # names the read: EVERY copy the chain derives answers the SAME materialized
    # children — not equal ones, and not none at all. An implementation that
    # carried views on the first derivation but rebuilt a copy of a copy from its
    # declared members fails here.
    items = ({"id": 11, "sku": "A-100"}, {"id": 12, "sku": "B-200"})
    source = _order_view(id=1, name="Ada", items=items)
    renamed = _edited_copy({"action": "mutate", "on": 0, "set": {"name": "Mutant"}}, 0, source)
    restated = _edited_copy({"action": "mutate", "on": 1}, 1, renamed)
    assert renamed.roots[0]["items"] is items
    assert restated.roots[0]["items"] is items
    assert source.roots[0]["items"] is items


_ANIMAL_CASE = _case("m-inheritance-004")
_ANIMAL_MODEL = model_facts.load_case_metamodel(_ANIMAL_CASE)
_ANIMAL_IDENTITY = model_facts.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Animal").identity


def _abstract_read_of_a_dog(**overrides: object) -> Any:
    # What an ABSTRACT-target read publishes: one complete concrete instance —
    # Dog's own `barkVolume` beside the root's members — plus the framework's
    # `familyVariant` provenance key, all under the query's abstract target.
    node: dict[str, object] = {
        "id": 1,
        "name": "Rex",
        "ownerId": 10,
        "licenseId": "L-100",
        "barkVolume": 7,
        "familyVariant": "Dog",
    }
    return _scenario_result(node | overrides, identity=_ANIMAL_IDENTITY)


def _edited_animal(authored: Mapping[str, object], source: Any) -> Any:
    step = {"action": "mutate", "on": 0, "set": dict(authored)}
    return snapshot._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
        _ANIMAL_CASE, _ANIMAL_MODEL, step, 0, source
    )


def test_edited_copy_judges_a_subtype_member_against_the_node_it_edits() -> None:
    # The read's target is the ABSTRACT `Animal`, which declares no `barkVolume`
    # at all; the node is a `Dog`, which declares it as an `int32`. Judging
    # against the target would wave the string through, because a name the
    # position does not declare is nobody's assignment to refuse.
    with pytest.raises(EngineError, match="does not match the declared type"):
        _edited_animal({"barkVolume": "loud"}, _abstract_read_of_a_dog())


def test_edited_copy_refuses_an_assignment_to_read_time_provenance() -> None:
    # `familyVariant` is a key the read publishes, not a member anything on the
    # node's ancestry declares, so a gate asking the materialized mapping would
    # accept it and carry a node claiming to be a `Cat`. The gate asks the model.
    with pytest.raises(EngineError, match="Dog has no assignable member of"):
        _edited_animal({"familyVariant": "Cat"}, _abstract_read_of_a_dog())


def test_edited_copy_refuses_a_sibling_branchs_member() -> None:
    # `indoor` is declared on `Cat`, the sibling concrete branch: it is no more
    # assignable on a `Dog` node than a name the family declares nowhere.
    with pytest.raises(EngineError, match="Dog has no assignable member of"):
        _edited_animal({"indoor": True}, _abstract_read_of_a_dog())


def test_edited_copy_carries_the_concrete_identity_its_node_resolves_to() -> None:
    # The accepted half: a member the node's own concrete Entity declares lands,
    # and the copy states the Entity it IS rather than the abstract target that
    # published it — so a chain of edits keeps judging against `Dog`.
    copy = _edited_animal({"barkVolume": 9}, _abstract_read_of_a_dog())
    assert (
        copy.identity
        == model_facts.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Dog").identity
    )
    assert copy.roots[0]["barkVolume"] == 9
    assert _edited_animal({"barkVolume": 3}, copy).identity == copy.identity


def test_edited_copy_refuses_a_variant_naming_no_concrete_subtype() -> None:
    # An unresolvable variant is refused rather than fallen back on: judging
    # against the abstract target instead is exactly the hole the resolution
    # closes, so it may not be the failure mode when resolution fails.
    with pytest.raises(EngineError, match="no concrete subtype of Animal"):
        _edited_animal({"name": "Rexy"}, _abstract_read_of_a_dog(familyVariant="Unicorn"))


def test_edited_copy_judges_a_concrete_target_read_against_that_target() -> None:
    # A CONCRETE-target read carries no `familyVariant` at all (`m-case-format`):
    # the caller already knows the variant, so a node states no provenance to
    # resolve and the target it was published under is the Entity it is.
    dog = model_facts.case_entity(_ANIMAL_MODEL, "parallax.compatibility.Dog").identity
    step = {"action": "mutate", "on": 0, "set": {"barkVolume": 9}}
    source = _scenario_result({"id": 1, "name": "Rex", "barkVolume": 7}, identity=dog)
    copy = snapshot._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
        _ANIMAL_CASE, _ANIMAL_MODEL, step, 0, source
    )
    assert (copy.identity, copy.roots[0]["barkVolume"]) == (dog, 9)


_TICKET = EntityIdentity("catalog", "Ticket")

# A STANDALONE Entity declaring an ordinary Attribute spelled `familyVariant`,
# which `m-inheritance` reserves from declared members on an inheritance
# PARTICIPANT alone. A read of one publishes that key holding domain data.
_TICKET_MODEL = form_metamodel(
    source(
        Declaration(
            identity=_TICKET,
            container=Table("ticket"),
            attributes=(key(_TICKET), attribute(_TICKET, "familyVariant", type=STRING)),
        )
    )
)


def _edited_ticket(authored: Mapping[str, object]) -> Any:
    step = {"action": "mutate", "on": 0, "set": dict(authored)}
    source_result = _scenario_result({"id": 1, "familyVariant": "premium"}, identity=_TICKET)
    return snapshot._edited_copy(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
        _case("m-snapshot-read-010"), _TICKET_MODEL, step, 0, source_result
    )


def test_edited_copy_reads_a_standalone_entitys_family_variant_as_domain_state() -> None:
    # Provenance is what that key means on a family, and nothing more: a
    # standalone Entity may declare a member of its own by that name, and
    # resolving its value as a variant spelling would refuse every edit of such a
    # node — even one touching another member entirely. It stays ordinary domain
    # state here: assignable, judged against its own declared type, and carried
    # by a copy that is still the Entity the read named.
    copy = _edited_ticket({"familyVariant": "standard"})
    assert copy.roots[0] == {"id": 1, "familyVariant": "standard"}
    assert copy.identity == _TICKET
    with pytest.raises(EngineError, match="does not match the declared type"):
        _edited_ticket({"familyVariant": 7})


def test_grade_mutate_step_rejects_an_on_index_naming_no_view() -> None:
    step = {"action": "mutate", "on": 5, "set": {"name": "Mutant"}}
    with pytest.raises(EngineError, match="holds no view to edit"):
        snapshot._grade_mutate_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
            _case("m-snapshot-read-010"), _ORDERS_MODEL, step, [_scenario_result({"id": 1})]
        )


def test_grade_mutate_step_publishes_no_copy_when_the_pin_rule_refuses() -> None:
    # A refused mutation derives nothing, so its slot stays empty and a later
    # step naming it is told so rather than handed a copy the verb never made.
    case = _case("m-bitemp-write-016")
    model = model_facts.load_case_metamodel(case)
    identity = model_facts.case_entity(model, "parallax.compatibility.Position").identity
    source = _scenario_result(
        {"id": 1, "value": decimal.Decimal("90.00")},
        pin=Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC), valid_time=None),
        identity=identity,
    )
    step = {
        "action": "mutate",
        "on": 0,
        "set": {"value": 999},
        "expectError": "transaction-time-pin-read-only",
    }
    error_class, result = snapshot._grade_mutate_step(case, model, step, [source])  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
    assert (error_class, result.roots, result.identity) == (
        "transaction-time-pin-read-only",
        (),
        None,
    )


# --------------------------------------------------------------------------- #
# Docker-free error paths (m-conformance-adapter's lane-honest ``EngineError``  #
# wrapping): a compiled/found query that fails inside `m-sql` / `m-navigate`  #
# / `m-temporal-read` is caught and re-raised as one `EngineError`, never a     #
# leaked lower-layer exception type.                                           #
# --------------------------------------------------------------------------- #
def test_check_action_step_rejects_a_managed_lifecycle_verb() -> None:
    # `load` is a managed-object surfacing this lane holds no state for; the
    # two verbs it does grade over a snapshot graph (`mutate`, `access`) pass.
    with pytest.raises(EngineError, match="graded by the API"):
        snapshot._check_action_step(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
            _case("m-snapshot-read-010"), {"action": "load"}
        )
    snapshot._check_action_step(_case("m-snapshot-read-010"), {"action": "mutate"})  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
    snapshot._check_action_step(_case("m-snapshot-read-010"), {"action": "access"})  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly


def test_compile_scenario_case_snapshot_lane_requires_an_object_query() -> None:
    when = {
        "scenario": [
            {"action": "mutate", "on": 0, "set": {"x": 1}},
            {"roundTrips": 1},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="needs `objectQuery`"):
        _compile(case, "postgres")


def test_compile_scenario_case_snapshot_lane_wraps_a_sql_gen_error() -> None:
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.nope", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="names no declared attribute"):
        _compile(case, "postgres")


def test_run_scenario_case_snapshot_lane_requires_an_object_query() -> None:
    when = {
        "scenario": [
            {"roundTrips": 1},
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="needs `objectQuery`"):
        _run(case, QueueDbPort([]))


def test_run_scenario_case_snapshot_lane_wraps_an_error_from_the_find_executor() -> None:
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.nope", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"x": 1}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="names no declared attribute"):
        _run(case, QueueDbPort([]))


_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": "A-100",
    "qty": 5,
    "price": decimal.Decimal("10.50"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 5),
}


def test_run_scenario_case_snapshot_lane_mutates_in_memory_with_no_writeback() -> None:
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    original = _case("m-snapshot-read-010")
    document = copy.deepcopy(cast("dict[str, Any]", original.document))
    document["when"]["scenario"][1]["expectRows"] = [{**_ORDER_ROW, "name": "Mutant"}]
    run = _run(dataclasses.replace(original, document=document), port)
    assert run.round_trips == 2
    assert [e.case_pointer for e in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/objectQuery",
    ]
    assert len(port.reads) == 2
    assert len(port.writes) == 0
    assert run.errors == []  # an unpinned mutate is accepted: no error observation
    assert [entry["at"] for entry in run.step_rows] == [
        "/scenario/0",
        "/scenario/1",
        "/scenario/2",
    ]
    assert run.step_rows[1]["rows"] == [
        {
            "id": 1,
            "name": "Mutant",
            "sku": "A-100",
            "qty": 5,
            "price": decimal.Decimal("10.50"),
            "active": True,
            "orderedOn": dt.date(2024, 1, 5),
        }
    ]


def test_run_scenario_case_snapshot_lane_refuses_a_set_the_read_cannot_assign() -> None:
    # The end-to-end half of the assignment: the `set` resolves against the
    # members the retained node's own Entity has, so a name that is no member of
    # it is refused at the verb rather than silently dropped.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"nickname": "Mutant"}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    with pytest.raises(EngineError, match="Order has no assignable member of"):
        _run(case, port)
    assert len(port.writes) == 0


def test_run_scenario_case_snapshot_lane_applies_out_of_band_statements() -> None:
    # `m-case-format` admits `given.apply` on a scenario without excluding the
    # action-bearing shape, so this lane owes the same setup every other executor
    # does: applied on the caller's own port before the first step, so each find
    # observes the state those statements left rather than the state they replaced.
    case = _case("m-snapshot-read-010")
    with_apply = dataclasses.replace(
        case,
        document={
            **case.document,
            "given": {"apply": [{"sql": "update orders set qty = ?", "binds": [9]}]},
        },
    )
    port = FakeWritePort(find_rows=[dict(_ORDER_ROW)])
    _run(with_apply, port)
    assert port.writes == [("update orders set qty = %s", [9])]


# --------------------------------------------------------------------------- #
# The scenario `expectError` grading (m-conformance-adapter `errors`): the      #
# snapshot lane's `mutate` runs the SAME finite-Transaction-Time-pin refusal    #
# the keyed developer verbs run, against the referenced find step's own         #
# statement pin, and reports one `errors` entry per matched `expectError`.      #
# --------------------------------------------------------------------------- #
_POSITION_R1_ROW: dict[str, object] = {
    "pos_id": 1,
    "acct_num": "A",
    "val": decimal.Decimal("90.00"),
    "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "thru_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
    "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
    "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
}


def test_run_scenario_case_grades_a_transaction_time_pin_read_only_mutate() -> None:
    port = FakeDbPort([dict(_POSITION_R1_ROW)])
    run = _run(_case("m-bitemp-write-016"), port)
    assert run.round_trips == 1
    assert [e.case_pointer for e in run.emissions] == ["/scenario/0/objectQuery"]
    assert run.errors == [{"at": "/scenario/1", "errorClass": "transaction-time-pin-read-only"}]


def test_run_scenario_case_accepts_a_finite_valid_time_pin_mutate() -> None:
    # The writable half of the finite-pin contrast: a finite Valid-Time pin
    # (Transaction Time defaulted Latest) passes the SAME validator, so the
    # mutate applies in-memory and no error observation is reported.
    row = dict(_POSITION_R1_ROW, val=decimal.Decimal("100.00"))
    port = FakeDbPort([row])
    run = _run(_case("m-bitemp-write-015"), port)
    assert run.round_trips == 1
    assert run.errors == []


def test_run_scenario_case_reports_an_undeclared_pin_refusal_loudly() -> None:
    # The mutate verb raised, but the step declares no expectError — a corpus/
    # implementation mismatch this lane names loudly, never a silently dropped
    # error observation.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Position",
                    "predicate": {"eq": {"attr": "Position.id", "value": 1}},
                    "temporal": {
                        "transaction-time": {"asOf": "2024-02-01T00:00:00.000000Z"},
                        "valid-time": {"asOf": "latest"},
                    },
                },
            },
            {"action": "mutate", "on": 0, "set": {"value": 999.00}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/position.yaml", "when": when})
    with pytest.raises(EngineError, match="declares no expectError"):
        _run(case, FakeDbPort([dict(_POSITION_R1_ROW)]))


def test_run_scenario_case_mutate_grading_rejects_an_out_of_range_on_index() -> None:
    # The grading wrapper guards `on` itself (its identity and pin lookups both
    # index the earlier steps' own recorded state), before any copy is derived.
    # One guard answers every way `on` can fail to name a step holding a view —
    # out of range, absent, or naming a write step, which holds none.
    when = {"scenario": [{"action": "mutate", "on": 5, "set": {"name": "Mutant"}}]}
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="holds no view to edit"):
        _run(case, FakeDbPort([]))


def test_run_scenario_case_reports_an_unraised_expect_error_loudly() -> None:
    # The step declares expectError but the mutation was accepted (the find
    # carries no finite Transaction-Time pin) — the same loud mismatch, the
    # other direction.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
            {
                "action": "mutate",
                "on": 0,
                "set": {"name": "Mutant"},
                "expectError": "transaction-time-pin-read-only",
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = FakeDbPort([{"id": 1, "name": "Ada"}])
    with pytest.raises(EngineError, match="but the mutation was accepted"):
        _run(case, port)


# --------------------------------------------------------------------------- #
# The scenario `expectGraph` grading (m-conformance-adapter `stepGraphs`), in   #
# its two placements. An `access` step over a relationship an earlier find      #
# step's own Include Paths materialized reads its contents off the RETAINED     #
# view — nothing at the port, which is what makes the observation about         #
# survival rather than about the database (m-snapshot-read *Closed world*,      #
# composition). A FIND step reports what it materialized itself, which is the   #
# opposite claim and reaches the port by definition.                            #
# --------------------------------------------------------------------------- #
_ORDER_1_ITEM_ROWS: list[dict[str, object]] = [
    {"id": 12, "order_id": 1, "sku": "B-200", "quantity": 1, "shipped_on": dt.date(2024, 2, 15)},
    {"id": 11, "order_id": 1, "sku": "A-100", "quantity": 2, "shipped_on": None},
]


def _include_scenario_port() -> QueueDbPort:
    return QueueDbPort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])


def test_run_scenario_case_reports_an_access_step_graph_from_the_retained_view() -> None:
    run = _run(_case("m-snapshot-read-016"), _include_scenario_port())
    # The find's two levels are the only calls; the mutate and the access cost none.
    assert run.round_trips == 2
    assert run.errors == []
    assert [entry["at"] for entry in run.step_graphs] == ["/scenario/2"]
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType] - the node ids are ints behind the graph's object typing


def test_run_scenario_case_reports_a_snapshot_lane_finds_own_materialized_graph() -> None:
    # The read placement on the ACTION-step lane: a find there reports what it
    # materialized exactly as a `uow` lane find does, so one authored
    # `expectGraph` means the same thing wherever the scenario's own shape sends
    # it. Both entries appear, in step order, at their own pointers.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                },
                "expectGraph": {"Order": [{"id": 1}]},
            },
            {"action": "access", "on": 0, "path": "items", "expectGraph": {"OrderItem": []}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    run = _run(case, _include_scenario_port())
    assert [entry["at"] for entry in run.step_graphs] == ["/scenario/0", "/scenario/1"]
    root_graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    (root,) = root_graph["Order"]
    assert root["id"] == 1
    assert sorted(node["id"] for node in cast("list[dict[str, object]]", root["items"])) == [11, 12]  # pyright: ignore[reportArgumentType] - the node ids are ints behind the graph's object typing


def test_run_scenario_case_lets_an_edit_chain_name_the_copy_before_it() -> None:
    # The chain the corpus authors (`m-snapshot-read-022`) in its DB-free form: a
    # second `mutate` names the FIRST one's copy rather than the read, which
    # resolves only because an accepted edit publishes what it derived. Each hop
    # carries its predecessor's assignment, and the source the chain hangs off
    # still holds the read's own state and the SAME loaded items.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"action": "mutate", "on": 1},
            {"action": "access", "on": 0, "path": "items", "expectGraph": {"OrderItem": []}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    run = _run(case, _include_scenario_port())
    assert run.round_trips == 2  # the find's two levels; no hop of the chain costs one
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType] - the node ids are ints behind the graph's object typing


def _orders_access_scenario(access: dict[str, object], *, includes: bool) -> case_format.Case:
    query: dict[str, object] = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
    }
    if includes:
        query["includes"] = [{"segments": [{"rel": "Order.items"}]}]
    when = {"scenario": [{"objectQuery": query}, access]}
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


def test_run_scenario_case_access_without_expect_graph_reports_no_step_graph() -> None:
    # The observation is the case's own oracle answered: a step asserting no
    # contents reports none, exactly as a step raising no error reports none.
    case = _orders_access_scenario({"action": "access", "on": 0, "path": "items"}, includes=True)
    run = _run(case, _include_scenario_port())
    assert run.step_graphs == []


def test_run_scenario_case_access_step_graph_rejects_an_on_naming_no_view() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 5, "path": "items", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(EngineError, match="holds no view to navigate"):
        _run(case, _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_an_on_naming_a_derived_copy() -> None:
    # An accepted `mutate` publishes a copy so a LATER EDIT can name it, and a
    # copy does carry its source's loaded arms — but it materialized nothing, and
    # `m-case-format` has an access stating contents name the read that did. The
    # reference harness holds no copy at all and refuses this shape, so accepting
    # it here would make one authored `expectGraph` grade in one lane and be
    # refused in the other.
    when: dict[str, object] = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                    "includes": [{"segments": [{"rel": "Order.items"}]}],
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"action": "access", "on": 1, "path": "items", "expectGraph": {"OrderItem": []}},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    with pytest.raises(EngineError, match="derived its view rather than materializing it"):
        _run(case, _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_a_multi_source_on() -> None:
    # The `on` ARRAY form spans sources at different lowered coordinates, so no one
    # view holds contents gathered across them: a step stating contents names the
    # single read that materialized them, and the set is refused rather than read
    # as its first element.
    case = _orders_access_scenario(
        {"action": "access", "on": [0], "path": "items", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(EngineError, match="names ONE materializing read"):
        _run(case, _include_scenario_port())


def test_run_scenario_case_access_step_graph_needs_a_navigated_path() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "expectGraph": {"OrderItem": []}}, includes=True
    )
    with pytest.raises(EngineError, match="needs a `path`"):
        _run(case, _include_scenario_port())


def test_run_scenario_case_access_step_graph_refuses_an_unincluded_relationship() -> None:
    # `items` is a real relationship the find never included, so the view carries
    # no loaded arm for it — the unloaded state itself, which an access asserting
    # contents cannot be authored over.
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "path": "items", "expectGraph": {"OrderItem": []}},
        includes=False,
    )
    with pytest.raises(EngineError, match="carries no loaded 'items'"):
        _run(case, QueueDbPort([[dict(_ORDER_ROW)]]))


def test_run_scenario_case_access_step_graph_refuses_an_undeclared_relationship() -> None:
    case = _orders_access_scenario(
        {"action": "access", "on": 0, "path": "nope", "expectGraph": {"OrderItem": []}},
        includes=True,
    )
    with pytest.raises(EngineError, match="declares no relationship 'nope'"):
        _run(case, _include_scenario_port())


def test_run_scenario_case_access_step_graph_walks_a_to_one_arm() -> None:
    # The to-one arm: the loaded view carries a single nested node rather than a
    # sequence, so the traversal appends instead of extending.
    query = {
        "target": "OrderItem",
        "predicate": {"eq": {"attr": "OrderItem.id", "value": 11}},
        "includes": [{"segments": [{"rel": "OrderItem.order"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {
                "action": "access",
                "on": 0,
                "path": "order",
                "expectGraph": {"Order": [{"id": 1}]},
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = QueueDbPort([[dict(_ORDER_1_ITEM_ROWS[1])], [dict(_ORDER_ROW)]])

    run = _run(case, port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["Order"]] == [1]


# `OrderStatus.orderItemId` is nullable, so one status belongs to a line item and
# the other to the order alone — the loaded-NULL to-one branch a deeper hop must
# tell apart from an unloaded view.
_STATUS_ON_ITEM: dict[str, object] = {
    "id": 201,
    "order_id": 1,
    "order_item_id": 11,
    "code": "PICKED",
}
_STATUS_ON_ORDER_ALONE: dict[str, object] = {
    "id": 204,
    "order_id": 1,
    "order_item_id": None,
    "code": "OPEN",
}
_ITEM_11_STATUS_ROWS: list[dict[str, object]] = [
    {"id": 202, "order_id": 1, "order_item_id": 11, "code": "PACKED"},
    dict(_STATUS_ON_ITEM),
]


def _status_root_access(includes: list[dict[str, object]], access: dict[str, object]):
    query = {
        "target": "OrderStatus",
        "predicate": {"eq": {"attr": "OrderStatus.orderId", "value": 1}},
        "includes": includes,
    }
    when = {"scenario": [{"objectQuery": query}, access]}
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


def test_run_scenario_case_access_step_graph_drops_a_null_branch_before_a_deeper_hop() -> None:
    # A loaded-null to-one branch is not an unloaded view: its own deeper level saw
    # an EMPTY parent set, so it contributes no terminal node to a path that fans
    # out. Carrying the null into the next hop would report the whole access as an
    # access over a relationship the read never included.
    case = _status_root_access(
        [{"segments": [{"rel": "OrderStatus.orderItem"}, {"rel": "OrderItem.statuses"}]}],
        {
            "action": "access",
            "on": 0,
            "path": "orderItem.statuses",
            "expectGraph": {"OrderStatus": [{"id": 202}, {"id": 201}]},
        },
    )
    port = QueueDbPort(
        [
            [dict(_STATUS_ON_ITEM), dict(_STATUS_ON_ORDER_ALONE)],
            [dict(_ORDER_1_ITEM_ROWS[1])],
            [dict(row) for row in _ITEM_11_STATUS_ROWS],
        ]
    )

    run = _run(case, port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["OrderStatus"]] == [202, 201]


def test_run_scenario_case_access_step_graph_omits_a_terminal_null_after_a_fan_out() -> None:
    # The other side of the same rule at the LAST hop: a fanned-out path answers
    # its non-null terminals, so the status belonging to no line item contributes
    # nothing rather than a null node beside the real one.
    query = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
        "includes": [{"segments": [{"rel": "Order.statuses"}, {"rel": "OrderStatus.orderItem"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {
                "action": "access",
                "on": 0,
                "path": "statuses.orderItem",
                "expectGraph": {"OrderItem": [{"id": 11}]},
            },
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})
    port = QueueDbPort(
        [
            [dict(_ORDER_ROW)],
            [dict(_STATUS_ON_ITEM), dict(_STATUS_ON_ORDER_ALONE)],
            [dict(_ORDER_1_ITEM_ROWS[1])],
        ]
    )

    run = _run(case, port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert [node["id"] for node in graph["OrderItem"]] == [11]


class _QueueWritePort(QueueDbPort):
    """A queue-backed read port that also takes DML.

    The shape a snapshot scenario needs once a `write:` step sits between the
    find that materializes a view and the access that states its contents: the
    reads are still answered in order, and the writes are recorded rather than
    refused.
    """

    def __init__(self, responses: Sequence[list[Row]]) -> None:
        super().__init__(responses)
        self.writes: list[tuple[str, list[object]]] = []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.writes.append((sql, list(binds)))
        return 1

    def transaction[T](
        self, body: Callable[[DatabaseConnection], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:
        return body_outcome(self, body)


def _write_between_find_and_access(write: object) -> case_format.Case:
    query = {
        "target": "Order",
        "predicate": {"eq": {"attr": "Order.id", "value": 1}},
        "includes": [{"segments": [{"rel": "Order.items"}]}],
    }
    when = {
        "scenario": [
            {"objectQuery": query},
            {"write": write, "roundTrips": 2},
            {
                "action": "access",
                "on": 0,
                "path": "items",
                "expectGraph": {"OrderItem": [{"id": 12}, {"id": 11}]},
            },
        ]
    }
    return _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})


_ORDER_NAME_UPDATE: list[dict[str, object]] = [
    {
        "mutation": "update",
        "entity": "parallax.compatibility.Order",
        "rows": [{"id": 1, "name": "Rewritten"}],
    }
]


def _ledger_write_after_find_and_mutate(write: object) -> case_format.Case:
    """A snapshot-lane scenario over the Transaction-Time-Only Ledger: the find
    materializes the one CURRENT milestone of id 2 (the fixture key holding
    exactly one, so a write naming no observed edge resolves unambiguously), a
    `mutate` puts the scenario on this lane, and the write step is whatever the
    caller states."""
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "parallax.compatibility.Ledger",
                    "predicate": {"eq": {"attr": "parallax.compatibility.Ledger.id", "value": 2}},
                    "temporal": {"transaction-time": {"asOf": "latest"}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"acctNum": "Z"}},
            {"write": write, "roundTrips": 2},
        ]
    }
    return _synthetic_write(
        "scenario",
        {
            "model": "models/ledger.yaml",
            "when": {"uow": {"concurrency": "optimistic"}, **when},
        },
    )


_LEDGER_2_ROW: dict[str, object] = {
    "led_id": 2,
    "acct_num": "B",
    "val": decimal.Decimal("200.00"),
    "in_z": dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
    "out_z": INFINITY,
}

_LEDGER_VALUE_UPDATE: list[dict[str, object]] = [
    {
        "mutation": "update",
        "entity": "parallax.compatibility.Ledger",
        "rows": [{"id": 2, "value": decimal.Decimal("300.00")}],
        "at": "2024-05-01T00:00:00+00:00",
    }
]


def test_run_scenario_case_write_step_commits_and_leaves_the_retained_view_standing() -> None:
    # The composition the closed-world clause is about: the write is its own unit
    # of work — a resolving read and then its DML — and the view the find
    # materialized stands across it, so the access still answers what THAT read
    # fetched with nothing at the port of its own.
    port = _QueueWritePort(
        [
            [dict(_ORDER_ROW)],
            [dict(row) for row in _ORDER_1_ITEM_ROWS],
            [dict(_ORDER_ROW)],
        ]
    )

    run = _run(_write_between_find_and_access(_ORDER_NAME_UPDATE), port)

    assert [emission.case_pointer for emission in run.emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/0/objectQuery",
        "/scenario/1/write",
    ]
    assert [sql for sql, _binds in port.writes] == ["update orders set name = %s where id = %s"]
    assert run.round_trips == 4  # the find's two levels, the write's resolve and its DML
    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert sorted(node["id"] for node in graph["OrderItem"]) == [11, 12]  # pyright: ignore[reportArgumentType] - the node ids are ints behind the graph's object typing


def test_run_scenario_case_refuses_a_non_keyed_write_step_on_the_snapshot_lane() -> None:
    # A legacy string label states no instruction at all, so there is nothing to
    # lower as the keyed buffer this lane executes and no question about the
    # lane's own shape behind the refusal — which is what keeps it apart from the
    # two predicate forms below, each refused for a reason of its own.
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(EngineError, match="BUFFERED KEYED instruction list"):
        _run(_write_between_find_and_access("insert"), port)
    assert port.writes == []


def test_run_scenario_case_names_the_case_when_a_snapshot_lane_write_will_not_lower() -> None:
    # A write step this lane cannot lower fails as a case-named EngineError rather
    # than as a raw planner exception crossing the conformance seam — the same
    # posture the unit-of-work lane takes for its own ungrouped write step.
    mis_authored = [
        {
            "mutation": "update",
            "entity": "parallax.compatibility.Order",
            "rows": [{"id": 1, "nope": 3}],
        }
    ]
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(EngineError, match="undeclared member"):
        _run(_write_between_find_and_access(mis_authored), port)
    assert port.writes == []


def test_compile_scenario_case_lowers_a_snapshot_lane_write_step() -> None:
    # The compile peer of the run lane above: a scenario carrying an action step
    # compiles through the snapshot path, whose find is instance-form and unlocked
    # and whose write step is lowered by the SAME planner the unit-of-work lane's
    # ungrouped write step uses.
    when = {
        "scenario": [
            {
                "objectQuery": {
                    "target": "Order",
                    "predicate": {"eq": {"attr": "Order.id", "value": 1}},
                }
            },
            {"action": "mutate", "on": 0, "set": {"name": "Mutant"}},
            {"write": _ORDER_NAME_UPDATE, "roundTrips": 2},
        ]
    }
    case = _synthetic_write("scenario", {"model": "models/orders.yaml", "when": when})

    emissions, round_trips = _compile(case, "postgres")

    assert [emission.case_pointer for emission in emissions] == [
        "/scenario/0/objectQuery",
        "/scenario/2/write",
    ]
    assert emissions[1].sql == "update orders set name = ? where id = ?"
    assert round_trips == 2


def test_run_scenario_case_refuses_a_materializing_predicate_write_on_the_snapshot_lane() -> None:
    # A predicate write over a TEMPORAL target materializes: it resolves through
    # the find before it. A find on this lane materializes the view a later access
    # states, so the two step roles genuinely conflict and the refusal says so —
    # never the readless diagnosis below.
    value = "parallax.compatibility.Ledger.value"
    write = {
        "mutation": "update",
        "target": {
            "entity": "parallax.compatibility.Ledger",
            "predicate": {"lessThan": {"attr": value, "value": "500.00"}},
        },
        "assignments": [{"attr": value, "value": "5.00"}],
        "at": "2024-05-01T00:00:00+00:00",
    }
    port = _QueueWritePort([[dict(_LEDGER_2_ROW)]])
    with pytest.raises(EngineError, match="MATERIALIZING predicate write"):
        _run(_ledger_write_after_find_and_mutate(write), port)
    assert port.writes == []


def test_run_scenario_case_refuses_a_readless_predicate_write_on_the_snapshot_lane() -> None:
    # An UNVERSIONED, non-temporal target owes no resolving read, so nothing about
    # the shape conflicts with this lane: it is refused as unwired, which is a
    # different fact about a different form than the materializing refusal above.
    write = {
        "mutation": "delete",
        "target": {
            "entity": "parallax.compatibility.OrderItem",
            "predicate": {
                "lessThan": {"attr": "parallax.compatibility.OrderItem.quantity", "value": 5}
            },
        },
    }
    port = _QueueWritePort([[dict(_ORDER_ROW)], [dict(row) for row in _ORDER_1_ITEM_ROWS]])
    with pytest.raises(EngineError, match="READLESS predicate write"):
        _run(_write_between_find_and_access(write), port)
    assert port.writes == []


def test_snapshot_lane_compile_and_run_reach_the_same_temporal_dml() -> None:
    # Compile seeds the same fixture milestones the run lane does, so a temporal
    # close on this lane resolves the milestone persisted history holds instead of
    # refusing for want of an observation. The two lanes must reach the SAME DML
    # for the same case, which is the whole reason this lane has a compile path —
    # so the run's own emissions ARE the compile oracle here, not a transcription
    # of one.
    case = _ledger_write_after_find_and_mutate(_LEDGER_VALUE_UPDATE)
    # The find, then the resolving read the keyed write's own unit of work owes.
    port = _QueueWritePort([[dict(_LEDGER_2_ROW)], [dict(_LEDGER_2_ROW)]])

    compiled, _round_trips = _compile(case, "postgres")
    run = _run(case, port)

    assert [(e.case_pointer, e.sql, e.binds) for e in compiled] == [
        (e.case_pointer, e.sql, e.binds) for e in run.emissions
    ]
    assert [e.sql for e in compiled[1:]] == [
        "update ledger set out_z = ? where led_id = ? and out_z = ? and in_z = ?",
        "insert into ledger(led_id, acct_num, val, in_z, out_z) values (?, ?, ?, ?, ?)",
    ]
    # The close addresses the FIXTURE milestone's own edge and the successor
    # carries its acct_num forward: both are facts only a seeded tracker holds.
    assert compiled[1].binds[3] == dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    assert compiled[2].binds[:3] == (2, "B", decimal.Decimal("300.00"))


def test_run_scenario_case_access_step_graph_keeps_an_all_to_one_terminal_null() -> None:
    # An all-to-one path fans out nowhere, so it answers one terminal per root and
    # a branch that reached no row IS that terminal: `null`, the state a case
    # authors as a to-one member and grades distinctly from a node.
    case = _status_root_access(
        [{"segments": [{"rel": "OrderStatus.orderItem"}, {"rel": "OrderItem.order"}]}],
        {
            "action": "access",
            "on": 0,
            "path": "orderItem.order",
            "expectGraph": {"Order": [None]},
        },
    )
    port = QueueDbPort([[dict(_STATUS_ON_ORDER_ALONE)]])

    run = _run(case, port)

    graph = cast("dict[str, list[dict[str, object]]]", run.step_graphs[0]["graph"])
    assert graph["Order"] == [None]


def test_judged_assignments_reject_an_invalid_member() -> None:
    account = models.load_models()["account"]
    account_entity = next(item for item in account.entities if item.identity.name == "Account")
    case = _synthetic_write("scenario", {"model": "models/account.yaml"})
    with pytest.raises(EngineError, match="invalid assignment"):
        snapshot._judged_assignments(  # pyright: ignore[reportPrivateUsage] - unit test drives the snapshot lane's private helper directly
            case,
            account,
            account_entity.identity,
            {"missing": 1},
            {"id": 1},
        )
