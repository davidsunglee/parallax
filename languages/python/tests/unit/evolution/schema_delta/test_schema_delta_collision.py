"""A derived Physical Index Name two objects claim (m-schema-delta), Docker-free.

A 128-bit fingerprint collision is a defensive backstop, not a control path: no
accepted model reaches it, and the fingerprint is stubbed here because that is
the only way to reach the branch at all. A table or sequence a binding names
like a derived name reaches it without a stub. What the tests pin is the REPORT
— that a clash is refused rather than silently renamed, and that the refusal
names every group, every object in it, and where each occurs.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Literal

import pytest

from parallax.core import InternalError
from parallax.core.internal.base import STRING
from parallax.core.internal.database_binding import PhysicalSequence, ResolvedBinding
from parallax.core.internal.dialect import POSTGRES, Dialect, PhysicalIndexName
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import (
    AttributeIdentity,
    Column,
    EntityIdentity,
    IndexIdentity,
)
from parallax.core.internal.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.internal.storage_layout import _temporal as temporal_naming
from parallax.descriptor import domain_model_from_yaml
from parallax.descriptor._records import Attribute, Entity, Index, Metamodel
from parallax.evolution.internal.model_evolution import (
    ABSENT,
    UnilateralEvolution,
    evolve_resolved,
)
from parallax.evolution.internal.schema_delta import (
    PHYSICAL_INDEX_NAME_COLLISION,
    CreatedIndex,
    schema_delta,
)
from parallax.evolution.internal.schema_delta import _naming as naming
from parallax.evolution.internal.schema_delta._naming import (
    NamedIndex,
    census,
    collision_groups,
    relation_census,
)
from parallax.evolution.internal.schema_delta._physical import (
    IndexDefinition,
    PhysicalColumn,
    TemporalBackingIndex,
)
from parallax.evolution.internal.schema_delta._plan import temporal_backing_indices
from parallax.evolution.internal.schema_delta._values import (
    CollidingRelation,
    CollidingTemporalConstraint,
    CollisionGroup,
    IndexPresence,
)
from parallax.postgres import PostgresBinding, PostgresLocation, PostgresSequence, PostgresTable
from tests._support.bindings import (
    TEST_BINDING,
    binding_for,
    bound_model,
    physical_table,
    resolved_table,
)
from tests._support.errors import raises_code
from tests.unit._corpus_model_support import corpus, corpus_records, formed
from tests.unit._inheritance_family_support import entity_with_two_indices_over_one_column

_ENTITY = EntityIdentity(namespace="parallax.test", name="Widget")
_OTHER = EntityIdentity(namespace="parallax.test", name="Gadget")


def _owner(table: str) -> EntityIdentity:
    """The standalone Entity owning ``table``."""
    return EntityIdentity(namespace="parallax.test", name=table.title())


def _definition(
    entity: EntityIdentity,
    index: str,
    *,
    unique: bool = False,
    table: str | None = None,
    owner: EntityIdentity | None = None,
) -> IndexDefinition:
    return IndexDefinition(
        table=resolved_table(
            owner or (entity if table is None else _owner(table)), table or entity.name.lower()
        ),
        index=IndexIdentity(entity, index),
        components=(AttributeIdentity(entity, "code"),),
        column_attributes=(AttributeIdentity(entity, "code"),),
        columns=(PhysicalColumn(Column(name="code"), STRING, 8, nullable=True),),
        unique=unique,
    )


_SHARED = PhysicalIndexName("pxi_widget_code_00000000000000000000000000000000")
_RECORDS_BALANCE = corpus_records()["balance"]


def _backing_indices(model: AcceptedMetamodel) -> tuple[TemporalBackingIndex, ...]:
    return temporal_backing_indices(bound_model(model))


def _entry(
    definition: IndexDefinition | TemporalBackingIndex,
    name: PhysicalIndexName = _SHARED,
    presence: IndexPresence = IndexPresence.LATER,
) -> NamedIndex:
    return NamedIndex(
        name=name,
        scope=definition.table.physical.qualifier,
        definition=definition,
        presence=presence,
    )


def _groups(entries: Sequence[NamedIndex]) -> tuple[CollisionGroup, ...]:
    """``entries`` grouped with every Table they name carried into the later model."""
    return collision_groups(entries, {entry.definition.mapping_owner for entry in entries})


def test_two_definitions_deriving_one_name_are_reported_as_a_group() -> None:
    widget = _definition(_ENTITY, "widget_code")
    gadget = _definition(_OTHER, "gadget_code", unique=True)
    (group,) = _groups([_entry(widget), _entry(gadget)])
    assert group.name == _SHARED
    # Canonical logical-identity order: Gadget precedes Widget.
    assert [definition.index.entity.name for definition in group.definitions] == [
        "Gadget",
        "Widget",
    ]
    reported = group.definitions[0]
    assert reported.table == physical_table("gadget")
    assert reported.index == IndexIdentity(_OTHER, "gadget_code")
    assert reported.components == (AttributeIdentity(_OTHER, "code"),)
    assert reported.unique is True


def test_a_name_only_one_definition_derives_is_no_group() -> None:
    widget = _definition(_ENTITY, "widget_code")
    gadget = _definition(_OTHER, "gadget_code")
    assert _groups([_entry(widget), _entry(gadget, PhysicalIndexName("pxi_gadget_code_1"))]) == ()


def test_each_definition_names_the_endpoints_it_occurs_in() -> None:
    # A clash may involve an Index the delta drops, one it creates, and one that
    # survives unchanged; the report says which, so a reader can tell an
    # already-deployed name apart from one about to be created.
    dropped = _definition(_ENTITY, "a_dropped")
    created = _definition(_ENTITY, "b_created")
    surviving = _definition(_ENTITY, "c_surviving")
    (group,) = _groups(
        [
            _entry(dropped, presence=IndexPresence.EARLIER),
            _entry(created, presence=IndexPresence.LATER),
            _entry(surviving, presence=IndexPresence.BOTH),
        ]
    )
    assert [definition.presence for definition in group.definitions] == [
        IndexPresence.EARLIER,
        IndexPresence.LATER,
        IndexPresence.BOTH,
    ]


def test_groups_are_reported_in_physical_index_name_order() -> None:
    first = PhysicalIndexName("pxi_aaa_0")
    second = PhysicalIndexName("pxi_bbb_0")
    groups = _groups(
        [
            _entry(_definition(_ENTITY, "one"), second),
            _entry(_definition(_OTHER, "two"), second),
            _entry(_definition(_ENTITY, "three"), first),
            _entry(_definition(_OTHER, "four"), first),
        ]
    )
    assert [group.name for group in groups] == [first, second]


def test_a_name_freed_before_it_is_taken_again_is_no_collision() -> None:
    # Statements run Table by Table, so an Index dropped from `a` is gone before
    # anything on `z` is created and the two definitions are never objects in the
    # database at once. Refusing here would refuse a delta that is executable.
    freed = _definition(_ENTITY, "freed", table="a")
    taken = _definition(_OTHER, "taken", table="z")
    assert (
        _groups(
            [
                _entry(freed, presence=IndexPresence.EARLIER),
                _entry(taken, presence=IndexPresence.LATER),
            ]
        )
        == ()
    )


def test_a_name_taken_before_it_is_freed_is_a_collision() -> None:
    # The same pair with the Tables exchanged: `a`'s create runs before `z`'s
    # drop, so both definitions hold the one name at that prefix. Coexistence is
    # the test, and the emitted order is what decides it.
    taken = _definition(_OTHER, "taken", table="a")
    freed = _definition(_ENTITY, "freed", table="z")
    (group,) = _groups(
        [
            _entry(freed, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ]
    )
    assert [entry.presence for entry in group.definitions] == [
        IndexPresence.LATER,
        IndexPresence.EARLIER,
    ]


def test_one_Table_creates_before_it_drops_so_its_own_pair_collides() -> None:
    # Within a Table an altered Index is created before its earlier definition is
    # dropped, so a dropped and a created definition there always overlap. This
    # is the collision a plan could never report: keyed by the shared name, it
    # emits neither statement.
    freed = _definition(_ENTITY, "freed")
    taken = _definition(_ENTITY, "taken")
    (group,) = _groups(
        [
            _entry(freed, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ]
    )
    assert len(group.definitions) == 2


def test_a_name_on_a_Table_the_delta_leaves_behind_is_never_freed() -> None:
    # No statement drops an Index from a Table the later endpoint does not hold,
    # so that definition is present throughout and collides with anything created
    # under its name.
    stranded = _definition(_ENTITY, "stranded", table="a")
    taken = _definition(_OTHER, "taken", table="z")
    (group,) = collision_groups(
        [
            _entry(stranded, presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ],
        {taken.mapping_owner},
    )
    assert len(group.definitions) == 2


def test_a_generated_delta_refuses_a_collision_rather_than_renaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Reaching the backstop needs the fingerprint to stop distinguishing, which
    # only a stub can do. What the generator must then NOT do is pick a different
    # name for one of them: a definition's name is its own.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(
            evolve_resolved(ABSENT, bound_model(entity_with_two_indices_over_one_column()))
        )
    assert raised.value.args[1] == (
        "postgres derived colliding Physical Index Names: "
        "pxi_widget_widget_widget_code_00000000000000000000000000000000 is derived by "
        "unique Index Widget.widget_code_uq on px.widget (code) [later], "
        "unique Index Widget.widget_code_uq_dup on px.widget (code) [later]"
    )


def test_a_temporal_collision_reports_the_authored_components_without_the_axis_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    model = corpus()["temporal-authored-index"]
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(evolve_resolved(ABSENT, bound_model(model)))
    message = str(raised.value)
    assert (
        "Index parallax.compatibility.Assignment.assignment_code on px.assignment (code) "
        in message
    )
    assert "Index parallax.compatibility.Handle.handle_label on px.handle (label) " in message
    assert "in_z" not in message and "out_z" not in message


def test_a_collision_with_an_index_the_delta_never_touches_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The check spans the Indices that COEXIST, not the ones a statement names.
    # An Index both editions declare is never created or dropped, and it is still
    # an object in the database while the new one is created beside it, so a name
    # it already holds is a name the delta cannot take.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(_gaining_a_second_index())
    assert raised.value.args[1].endswith(
        "unique Index Widget.widget_code_uq on px.widget (code) [both], "
        "unique Index Widget.widget_code_uq_dup on px.widget (code) [later]"
    )


def test_a_delta_that_frees_a_name_before_taking_it_is_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End to end on the pair the census must NOT refuse: `a` loses the Index and
    # `z` gains one deriving the same name. The drop runs first, so the name is
    # free when the create runs, and the generator owes the statements.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    delta = schema_delta(_moving_an_index("a", "z"))
    assert delta.statements == (
        "drop index px.pxi_index_00000000000000000000000000000000",
        "create index pxi_index_00000000000000000000000000000000 on px.z (code)",
    )


def test_a_delta_that_takes_a_name_before_freeing_it_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same two Entities with their Tables exchanged. Now the create runs
    # first and the name is still held, so the delta is not executable and is
    # refused instead of emitted.
    monkeypatch.setattr(naming, "_fingerprint", _one_fingerprint)
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(_moving_an_index("z", "a"))
    assert raised.value.args[1] == (
        "postgres derived colliding Physical Index Names: "
        "pxi_index_00000000000000000000000000000000 is derived by "
        "Index Anvil.code_ix on px.a (code) [later], Index Zither.code_ix on px.z (code) [earlier]"
    )


_ONE_NAME: Dialect = dataclasses.replace(POSTGRES, max_identifier_bytes=37)
"""A Dialect whose limit leaves no readable prefix, so with the fingerprint
stubbed every definition derives the one name ``pxi_index_<zeros>``."""


def _one_fingerprint(definition: IndexDefinition) -> str:
    del definition
    return "0" * 32


def _moving_an_index(earlier_table: str, later_table: str) -> UnilateralEvolution:
    """One authored Index dropped from one Table and declared on another."""
    one_name = binding_for(_ONE_NAME)
    evolution = evolve_resolved(
        ResolvedBinding(_indexed(earlier_table), one_name),
        ResolvedBinding(_indexed(later_table), one_name),
    )
    assert isinstance(evolution, UnilateralEvolution)
    return evolution


def _indexed(table: str) -> AcceptedMetamodel:
    """Two Entities on Tables ``a`` and ``z``, only ``table`` declaring an Index."""
    return formed(
        Metamodel(
            entities=tuple(
                Entity(
                    name=name,
                    table=name[:1].lower(),
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(name="code", type="string", column="code", max_length=8),
                    ),
                    indices=(
                        (Index(name="code_ix", attributes=("code",)),)
                        if name[:1].lower() == table
                        else ()
                    ),
                )
                for name in ("Anvil", "Zither")
            )
        )
    )


def _gaining_a_second_index() -> UnilateralEvolution:
    """Declaring a second Index beside one both endpoints already hold."""
    evolution = evolve_resolved(
        bound_model(_widget_with_one_index()),
        bound_model(entity_with_two_indices_over_one_column()),
    )
    assert isinstance(evolution, UnilateralEvolution)
    return evolution


def _widget_with_one_index() -> AcceptedMetamodel:
    """``entity_with_two_indices_over_one_column`` before the second Index."""
    return formed(
        Metamodel(
            entities=(
                Entity(
                    name="Widget",
                    table="widget",
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(name="code", type="string", column="code", max_length=8),
                    ),
                    indices=(Index(name="widget_code_uq", attributes=("code",), unique=True),),
                ),
            )
        )
    )


def _backing(
    kind: Literal["primaryKey", "exclusion"], table: str = "widget"
) -> TemporalBackingIndex:
    return TemporalBackingIndex(
        table=resolved_table(_owner(table), table),
        kind=kind,
        columns=(Column(name="id"), Column(name="out_z")),
        name=_SHARED,
    )


def test_a_temporal_constraint_sharing_an_authored_name_is_reported_by_its_kind() -> None:
    widget = _definition(_ENTITY, "widget_code")
    (group,) = _groups([_entry(_backing("exclusion")), _entry(widget)])
    (authored,) = group.definitions
    assert authored.index == widget.index
    (temporal,) = group.temporal_constraints
    assert temporal == CollidingTemporalConstraint(
        table=physical_table("widget"),
        kind="exclusion",
        columns=(Column(name="id"), Column(name="out_z")),
        presence=IndexPresence.LATER,
    )


def test_a_temporal_constraint_is_never_dropped_so_it_never_frees_its_name() -> None:
    # An authored Index freed before another is created gives the name up; a
    # temporal constraint the later model no longer names is not dropped by any
    # delta, so it still holds the name when the other is created.
    taken = _definition(_OTHER, "taken", table="z")
    (group,) = collision_groups(
        [
            _entry(_backing("primaryKey", "a"), presence=IndexPresence.EARLIER),
            _entry(taken, presence=IndexPresence.LATER),
        ],
        {_owner("a"), taken.mapping_owner},
    )
    assert [entry.presence for entry in group.definitions] == [IndexPresence.LATER]
    assert [entry.presence for entry in group.temporal_constraints] == [IndexPresence.EARLIER]


def test_the_census_tells_holding_tables_apart_by_mapping_owner_not_declared_name() -> None:
    # One root-declared Index on two table-per-concrete-subtype concretes whose
    # declared names are equal still names two physical objects, so neither
    # endpoint's definition is mistaken for the other's survivor.
    first = _definition(_ENTITY, "code_ix", table="shared", owner=_ENTITY)
    second = dataclasses.replace(first, table=resolved_table(_OTHER, first.table.physical.name))
    entries = census((first,), (second,), POSTGRES)
    assert [(entry.definition, entry.presence) for entry in entries] == [
        (first, IndexPresence.EARLIER),
        (second, IndexPresence.LATER),
    ]
    assert entries[0].name == entries[1].name


def test_an_unchanged_temporal_constraint_is_one_entry_present_throughout() -> None:
    model = formed(_RECORDS_BALANCE)
    later = _backing_indices(model)
    entries = census((), (), POSTGRES, earlier_temporal=later, later_temporal=later)
    assert [(entry.name.value[:7], entry.presence) for entry in entries] == [
        ("pxc_pk_", IndexPresence.BOTH),
        ("pxc_exc", IndexPresence.BOTH),
    ]
    assert collision_groups(entries, {backing.mapping_owner for backing in later}) == ()


def test_a_generated_delta_counts_temporal_constraints_in_the_census(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The two names a temporal Table compiles are its layout's own; stubbing
    # them to one shows that the census reads them rather than deriving any.
    def shared(table: object, kind: str, groups: object) -> str:
        del table, kind, groups
        return _SHARED.value

    monkeypatch.setattr(temporal_naming, "constraint_name", shared)
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(evolve_resolved(ABSENT, bound_model(formed(_RECORDS_BALANCE))))
    assert raised.value.args[1] == (
        f"postgres derived colliding Physical Index Names: {_SHARED.value} is derived by "
        "temporal exclusion on px.balance (bal_id, in_z, out_z) [later], "
        "temporal primaryKey on px.balance (bal_id, out_z) [later]"
    )


_PLACED_YAML = """
entities:
  - name: Anvil
    table: anvil
    attributes:
      - name: id
        type: int64
        primaryKey: true
        pkGeneration: { strategy: sequence, name: anvilIds }
      - { name: code, type: string, maxLength: 8 }
    indices:
      - { name: code_ix, attributes: [code] }
  - name: Zither
    table: zither
    attributes:
      - { name: id, type: int64, primaryKey: true }
"""
_PLACED: AcceptedMetamodel = model_of(domain_model_from_yaml(_PLACED_YAML))


def _derived() -> CreatedIndex:
    """The one authored Index of ``_PLACED``, as the default binding derives it."""
    (created,) = schema_delta(evolve_resolved(ABSENT, bound_model(_PLACED))).created_indices
    return created


def _placed_under(binding: PostgresBinding) -> UnilateralEvolution:
    return evolve_resolved(ABSENT, ResolvedBinding(_PLACED, binding))


def test_a_table_bound_under_a_derived_index_name_is_refused() -> None:
    name = _derived().physical_index_name.value
    binding = PostgresBinding(
        default=PostgresLocation(schema="px"), entities={"Zither": PostgresTable(name=name)}
    )
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(_placed_under(binding))
    assert raised.value.args[1] == (
        f"postgres derived colliding Physical Index Names: {name} is derived by "
        f"Index Anvil.code_ix on px.anvil (code) [later] and held by table px.{name} [later]"
    )


def test_a_sequence_bound_under_a_derived_index_name_is_refused() -> None:
    name = _derived().physical_index_name.value
    binding = PostgresBinding(
        default=PostgresLocation(schema="px"),
        sequences={"anvilIds": PostgresSequence(name=name)},
    )
    with raises_code(InternalError, PHYSICAL_INDEX_NAME_COLLISION) as raised:
        schema_delta(_placed_under(binding))
    assert raised.value.args[1].endswith(f"and held by sequence px.{name} [later]")


def test_a_relation_holding_the_name_in_another_schema_is_no_collision() -> None:
    name = _derived().physical_index_name.value
    binding = PostgresBinding(
        default=PostgresLocation(schema="px"),
        entities={"Zither": PostgresTable(schema="other", name=name)},
    )
    assert schema_delta(_placed_under(binding)).created_indices == (_derived(),)


def test_a_temporal_constraint_name_held_by_a_table_is_refused() -> None:
    model = formed(_RECORDS_BALANCE)
    (constraints,) = (
        table.temporal_constraints
        for table in bound_model(model).tables
        if table.temporal_constraints is not None
    )
    groups = collision_groups(
        census((), (), POSTGRES, later_temporal=_backing_indices(model)),
        set(),
        (CollidingRelation(physical_table(constraints.exclusion_name), IndexPresence.EARLIER),),
    )
    (group,) = groups
    assert group.name.value == constraints.exclusion_name
    assert [constraint.kind for constraint in group.temporal_constraints] == ["exclusion"]


def test_only_a_qualifier_scoped_dialect_counts_relations() -> None:
    later = ResolvedBinding(_PLACED, TEST_BINDING)
    assert relation_census(later, later, POSTGRES) == (
        CollidingRelation(physical_table("anvil"), IndexPresence.BOTH),
        CollidingRelation(physical_table("zither"), IndexPresence.BOTH),
        CollidingRelation(PhysicalSequence(("px",), "anvilIds"), IndexPresence.BOTH),
    )
    per_table = dataclasses.replace(POSTGRES, index_name_scope="table")
    assert relation_census(later, later, per_table) == ()
