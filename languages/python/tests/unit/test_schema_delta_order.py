"""Executable statement order (m-schema-delta), Docker-free.

`_order` sorts by one total key instead of walking a dependency graph, which is
sound only while that key is a linear extension of the dependency rules. These
tests state the rules independently — through the invariant walker — and then
check the key against them, so the shortcut cannot silently stop being valid.
"""

from __future__ import annotations

from _corpus_model_support import corpus, formed
from _inheritance_family_support import entity_with_two_indices_over_one_column

from parallax.core.base import INT32, STRING
from parallax.core.dialect import POSTGRES, PhysicalIndexName
from parallax.core.metamodel import AttributeIdentity, Column, EntityIdentity, IndexIdentity, Table
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor._records import Attribute, Entity, Index, Inheritance, Metamodel
from parallax.evolution.model_evolution import ABSENT, EntityAdded, UnilateralEvolution, evolve
from parallax.evolution.schema_delta._order import dependency_violations, order, order_key
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    IndexDefinition,
    PhysicalColumn,
    PhysicalOperation,
    member_key,
    table_of,
)
from parallax.evolution.schema_delta._plan import plan

_MODELS = corpus()

_ENTITY = EntityIdentity(namespace="parallax.test", name="Widget")
_TABLE = Table(name="widget")
_CAUSE = (EntityAdded(entity=_ENTITY),)
_CODE = PhysicalColumn(Column(name="code"), STRING, 8, nullable=True)
_COUNT = PhysicalColumn(Column(name="count"), INT32, None, nullable=True)


def _index(name: str, column: PhysicalColumn = _CODE) -> IndexDefinition:
    return IndexDefinition(
        table=_TABLE,
        index=IndexIdentity(_ENTITY, name),
        components=(AttributeIdentity(_ENTITY, column.column.name),),
        columns=(column,),
        unique=False,
    )


def _create_table() -> CreateTable:
    return CreateTable(
        table=_TABLE, columns=(_CODE, _COUNT), primary_key=(Column(name="code"),), caused_by=_CAUSE
    )


def _create_index(name: str, column: PhysicalColumn = _CODE) -> CreateIndex:
    return CreateIndex(
        definition=_index(name, column), name=PhysicalIndexName(f"pxi_{name}"), caused_by=_CAUSE
    )


def _drop_index(name: str) -> DropIndex:
    return DropIndex(
        definition=_index(name), name=PhysicalIndexName(f"pxi_{name}_old"), caused_by=_CAUSE
    )


def _add_column(column: PhysicalColumn) -> AddColumn:
    return AddColumn(table=_TABLE, column=column, caused_by=_CAUSE)


# --- the key ------------------------------------------------------------------


def test_the_key_leads_with_the_physical_table() -> None:
    # One Table's statements stay together and the whole output stays stable
    # under an edit to an unrelated Table.
    other = CreateTable(table=Table(name="aardvark"), columns=(), primary_key=(), caused_by=_CAUSE)
    assert order_key(other) < order_key(_create_table())


def test_within_one_table_the_kind_decides() -> None:
    ordered = order([_drop_index("d"), _create_index("c"), _add_column(_COUNT), _create_table()])
    assert [type(operation).__name__ for operation in ordered] == [
        "CreateTable",
        "AddColumn",
        "CreateIndex",
        "DropIndex",
    ]


def test_two_operations_of_one_kind_sort_by_the_member_they_address() -> None:
    ordered = order([_create_index("second"), _create_index("first")])
    assert [member_key(operation) for operation in ordered] == ["pxi_first", "pxi_second"]


# --- the rules the key must satisfy -------------------------------------------


def test_an_executable_order_breaks_no_rule() -> None:
    ordered = order([_drop_index("d"), _create_index("d"), _add_column(_CODE), _create_table()])
    assert dependency_violations(ordered) == ()


def test_a_table_acted_on_before_it_exists_is_a_violation() -> None:
    violations = dependency_violations([_create_index("c"), _create_table()])
    assert violations == ("0: widget is acted on before it is created",)


def test_an_index_over_a_column_the_plan_has_not_added_yet_is_a_violation() -> None:
    plan_out_of_order: list[PhysicalOperation] = [_create_index("c"), _add_column(_CODE)]
    (violation,) = dependency_violations(plan_out_of_order)
    assert violation == "0: pxi_c indexes widget.code before that Column is added"


def test_dropping_an_altered_index_before_creating_its_target_is_a_violation() -> None:
    (violation,) = dependency_violations([_drop_index("d"), _create_index("d")])
    assert violation == (
        "0: pxi_d_old drops an altered Index before its target definition is created"
    )


def test_a_prerequisite_the_plan_does_not_contain_is_no_violation() -> None:
    # An operation on a Table this delta does not create acts on one the earlier
    # edition already had, and a drop with no matching create replaces nothing.
    assert dependency_violations([_create_index("c"), _drop_index("gone")]) == ()


def _tpcs_family_altering_a_root_declared_index(*, unique: bool) -> AcceptedMetamodel:
    """Two concrete Tables repeating one root-declared Index, whose uniqueness varies.

    One logical Index Identity with a physical projection per concrete Table is
    what makes a prerequisite keyed by the Identity alone ambiguous.
    """
    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="code", type="string", column="code", max_length=8),
        ),
        indices=(Index(name="root_code_ix", attributes=("code",), unique=unique),),
    )
    return formed(
        Metamodel(
            entities=(
                root,
                Entity(
                    name="Alpha",
                    table="alpha",
                    inheritance=Inheritance(role="concrete-subtype", parent="Root"),
                    attributes=(Attribute(name="x", type="int32", column="x"),),
                ),
                Entity(
                    name="Zeta",
                    table="zeta",
                    inheritance=Inheritance(role="concrete-subtype", parent="Root"),
                    attributes=(Attribute(name="y", type="int32", column="y"),),
                ),
            )
        )
    )


def test_one_logical_index_replaced_on_every_concrete_table_breaks_no_rule() -> None:
    # Each concrete Table holds its own create/drop pair for the same root-declared
    # Index Identity, and each drop's prerequisite is its OWN Table's create. A
    # rule keyed by the Identity alone would compare `alpha`'s drop against
    # `zeta`'s create and report an order that is in fact correct.
    evolution = evolve(
        _tpcs_family_altering_a_root_declared_index(unique=False),
        _tpcs_family_altering_a_root_declared_index(unique=True),
    )
    assert isinstance(evolution, UnilateralEvolution)
    ordered = order(plan(evolution, POSTGRES).operations)
    assert [(type(operation).__name__, table_of(operation).name) for operation in ordered] == [
        ("CreateIndex", "alpha"),
        ("DropIndex", "alpha"),
        ("CreateIndex", "zeta"),
        ("DropIndex", "zeta"),
    ]
    assert dependency_violations(ordered) == ()


def test_every_generated_plan_is_ordered_so_that_no_rule_is_broken() -> None:
    # The property over real models rather than over a hand-built plan.
    for model in (
        _MODELS["storage-layout"],
        _MODELS["error-cases"],
        _MODELS["payment"],
        _MODELS["rate"],
        entity_with_two_indices_over_one_column(),
    ):
        ordered = order(plan(evolve(ABSENT, model), POSTGRES).operations)
        assert dependency_violations(ordered) == ()


def test_every_incremental_plan_is_ordered_so_that_no_rule_is_broken() -> None:
    # The same property where the rules can actually bind: an incremental plan
    # is where a Column is added beside an Index over it and an altered Index is
    # created beside the drop it replaces. Every unilateral endpoint pair the
    # corpus authors is walked, so a lowering that grows a new dependency has to
    # keep the key a linear extension of the rules.
    pairs = [
        (_MODELS[stem], _MODELS[stem.removesuffix("-v1") + "-v2"])
        for stem in sorted(_MODELS)
        if stem.endswith("-v1") and stem.removesuffix("-v1") + "-v2" in _MODELS
    ]
    assert pairs
    for earlier, later in pairs:
        evolution = evolve(earlier, later)
        if not isinstance(evolution, UnilateralEvolution):
            continue
        assert dependency_violations(order(plan(evolution, POSTGRES).operations)) == ()
