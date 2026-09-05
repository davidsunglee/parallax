"""Provisioning through the shipped generator (m-schema-delta), Docker-free.

Provisioning is the Unilateral Evolution from ``ABSENT``, so these are the
generator's own proofs at its own interface: the ordered statements and the
created-Index provenance ``schema_delta`` returns for one accepted model. They
cover what the layout answers — canonical slot order, effective physical
nullability, the derived physical primary key, quoted reserved identifiers,
structured-document columns — under every mapping form, plus the naming,
ordering, refusal, and collision rules the generator itself owns.

The conformance provisioner is a caller of this path and holds no DDL of its own
(``test_provision.py``), which is what makes the whole database-backed suite a
proof of these statements.
"""

from __future__ import annotations

import dataclasses
import gc
from collections.abc import Iterator, Sequence
from types import ModuleType

import pytest
from _corpus_model_support import corpus, corpus_records, formed
from _document_layout_support import document_model
from _inheritance_family_support import (
    entity_with_two_indices_over_one_column,
    tpcs_family_with_a_root_declared_unique_index,
    tpcs_family_with_a_temporal_root,
    tpcs_family_with_a_value_object,
    tph_family_with_a_descendant_declared_value_object_and_index,
    tph_family_with_a_value_object,
)

from parallax.core.base import STRING
from parallax.core.dialect import (
    POSTGRES,
    Dialect,
    IndexColumnDdl,
    PhysicalIndexName,
    Unsupported,
)
from parallax.core.metamodel import AttributeIdentity, Column, EntityIdentity, IndexIdentity, Table
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.storage_layout import ColumnSlot
from parallax.evolution.model_evolution import ABSENT, UnilateralEvolution, evolve
from parallax.evolution.schema_delta import (
    PhysicalLocation,
    SchemaDelta,
    UnsupportedSchemaEvolutionError,
    schema_delta,
)
from parallax.evolution.schema_delta._physical import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropIndex,
    ExpandColumnDomain,
    IndexDefinition,
    PhysicalColumn,
    location_of,
    member_key,
)
from parallax.evolution.schema_delta._render import render

_RECORDS = corpus_records()
_MODELS = corpus()
_DOCUMENT = document_model()


def _delta(model: AcceptedMetamodel, dialect: Dialect = POSTGRES) -> SchemaDelta:
    """The whole provisioning delta for ``model``."""
    return schema_delta(evolve(ABSENT, model), dialect)


def _statements(model: AcceptedMetamodel, dialect: Dialect = POSTGRES) -> list[str]:
    return list(_delta(model, dialect).statements)


def _tables(model: AcceptedMetamodel) -> dict[str, str]:
    """Each ``create table`` statement of ``model``, keyed by its Table name."""
    return {
        statement.split(" ")[2]: statement
        for statement in _statements(model)
        if statement.startswith("create table ")
    }


def _storage_layout_ddl(table: str) -> str:
    return _tables(_MODELS["storage-layout"])[table]


def test_provisioning_quote_reserved_and_order_columns() -> None:
    (ddl,) = _statements(_MODELS["grade"])
    assert ddl == (
        'create table grade (id bigint not null, "order" integer not null, '
        "label varchar(32) not null, primary key (id))"
    )


def test_provisioning_map_value_objects_to_jsonb() -> None:
    (ddl,) = [
        stmt
        for stmt in _statements(_MODELS["customer"])
        if stmt.startswith("create table customer ")
    ]
    assert "address jsonb" in ddl
    assert "primary key (id)" in ddl


def test_provisioning_temporal_pk_is_business_key_plus_to_columns() -> None:
    # A temporal entity's physical PK is the business key plus each axis's end column
    # (m-storage-layout): audit-only Balance keys on (bal_id, out_z) so successive
    # milestones sharing one business key coexist, and every close-update pins the
    # key columns.
    audit = _tables(_MODELS["balance"])["balance"]
    assert "primary key (bal_id, out_z)" in audit
    # Bitemporal Position keys on the business key plus BOTH end columns, Valid Time
    # before Transaction Time (thru_z then out_z), which is the derived index's order.
    bitemporal = _tables(_MODELS["position"])["position"]
    assert "primary key (pos_id, thru_z, out_z)" in bitemporal


def test_provisioning_create_the_shared_table_once() -> None:
    # Payment (abstract root) is tableless; its concrete subtypes share ONE table,
    # so exactly one `create table payment` is emitted (not one per subtype).
    tables = _statements(_MODELS["payment"])
    payment_tables = [ddl for ddl in tables if ddl.startswith("create table payment ")]
    assert len(payment_tables) == 1


def test_provisioning_tph_merges_the_whole_family_plus_the_tag_column() -> None:
    # The shared `payment` table physically carries the root's own columns, the
    # tag column, and EVERY concrete's own column (nullable — a card row leaves
    # `tendered` null and a cash row leaves `card_network` null). The tag occupies
    # its own Discriminator tier, immediately after the identity slots.
    (ddl,) = [stmt for stmt in _statements(_MODELS["payment"]) if "payment" in stmt]
    assert ddl == (
        "create table payment (id bigint not null, kind varchar(32) not null, "
        "amount numeric(18, 2) not null, card_network varchar(16), "
        "tendered numeric(18, 2), primary key (id))"
    )


def test_provisioning_tph_intermediate_abstract_subtype_columns_are_merged_once() -> None:
    # Animal's shared table carries Pet's own `license_id` exactly once, even though
    # two of its three concretes (Dog, Cat) pass through the abstract subtype Pet.
    (ddl,) = [stmt for stmt in _statements(_MODELS["animal"]) if "animal" in stmt]
    assert ddl.count("license_id") == 1
    assert "kind varchar(32)" in ddl
    assert "bark_volume integer" in ddl
    assert "indoor boolean" in ddl
    assert "tusk_length numeric(18, 2)" in ddl


def test_provisioning_tpcs_creates_one_table_per_concrete_with_its_own_ancestry() -> None:
    # Table-per-concrete-subtype: no shared table, no tag column — each concrete's
    # OWN table physically carries its full ancestry-derived chain.
    tables = _statements(_MODELS["document"])
    (invoice,) = [t for t in tables if t.startswith("create table invoice ")]
    assert invoice == (
        "create table invoice (id bigint not null, title varchar(64) not null, "
        "folder_id bigint, currency varchar(3) not null, "
        "amount_due numeric(18, 2) not null, primary key (id))"
    )
    (memo,) = [t for t in tables if t.startswith("create table memo ")]
    assert "currency" not in memo  # Memo does not descend from FinancialDocument
    assert "kind" not in invoice and "kind" not in memo


def test_provisioning_tpcs_temporal_pk_includes_the_root_declared_axes() -> None:
    # Rate (models/rate.yaml): a table-per-concrete-subtype family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype (m-inheritance "Inherited members") — DepositRate/LoanRate
    # declare NO axes locally. The root derives the whole key, and each concrete
    # table carries it: the business key plus EACH axis's end column, never just
    # the business key alone, or a second milestone for the same id could not be
    # stored.
    tables = _statements(_MODELS["rate"])
    (deposit,) = [t for t in tables if t.startswith("create table deposit_rate ")]
    assert "primary key (id, thru_z, out_z)" in deposit
    (loan,) = [t for t in tables if t.startswith("create table loan_rate ")]
    assert "primary key (id, thru_z, out_z)" in loan
    # Quote (models/quote.yaml): the audit-only (single-axis) TPCS counterpart.
    (spot,) = _statements(_MODELS["quote"])
    assert "primary key (id, out_z)" in spot


def test_provisioning_tph_temporal_pk_includes_the_root_declared_axes() -> None:
    # Instrument (models/instrument.yaml): a table-per-hierarchy family whose
    # bitemporal axes are declared on the abstract ROOT and inherited by every
    # concrete subtype — Bond/Stock declare NO axes locally. The shared table's
    # physical PK must still be the business key plus EACH axis's end column,
    # never just the business key alone.
    (ddl,) = [stmt for stmt in _statements(_MODELS["instrument"]) if "instrument" in stmt]
    assert "primary key (id, thru_z, out_z)" in ddl


def test_provisioning_render_the_structured_column_last_and_not_null() -> None:
    marker, person = _statements(_DOCUMENT)
    assert person == (
        "create table person (id bigint not null, payload jsonb not null, primary key (id))"
    )
    # An Entity with no document-resident member still gets the column: the
    # layout is root-owned and every governed row carries a document.
    assert marker == (
        "create table marker (id bigint not null, payload jsonb not null, primary key (id))"
    )
    assert "default" not in person


def test_provisioning_standalone_slots_carry_declared_nullability() -> None:
    # A standalone Entity's slots apply to its table's only row owner, so each
    # keeps its declared answer; the identity slot is non-null because the
    # physical primary key selects it. The one top-level document occupies a
    # single `jsonb` column after every scalar tier.
    assert _storage_layout_ddl("layout_profile") == (
        "create table layout_profile (id bigint not null, label varchar(32) not null, "
        "note varchar(64), contact jsonb not null, primary key (id))"
    )


def test_provisioning_tph_requires_family_wide_but_not_subtype_only_slots() -> None:
    # `amount` is declared on the root, so it applies to every row owner of the
    # shared table and stays physically non-null. `cardNetwork` and `tendered` are
    # each REQUIRED of the concrete Entity declaring them, yet neither applies to
    # the sibling variant's rows, so both physical columns must permit NULL. The
    # framework-owned discriminator is never nullable.
    assert _storage_layout_ddl("layout_payment") == (
        "create table layout_payment (id bigint not null, kind varchar(32) not null, "
        "amount numeric(18, 2) not null, card_network varchar(16), "
        "tendered numeric(18, 2), primary key (id))"
    )


def test_provisioning_tpcs_tables_repeat_ancestry_and_may_reuse_a_column() -> None:
    # Each concrete table carries the root-owned ancestry slots followed by its own
    # member. The two sibling members are distinct contributors that map to the same
    # physical column spelling in structurally different tables, so each keeps its
    # declared non-null answer.
    assert _storage_layout_ddl("layout_audit") == (
        "create table layout_audit (id bigint not null, title varchar(64) not null, "
        "detail varchar(32) not null, primary key (id))"
    )
    assert _storage_layout_ddl("layout_survey") == (
        "create table layout_survey (id bigint not null, title varchar(64) not null, "
        "detail varchar(32) not null, primary key (id))"
    )


def test_provisioning_tph_maps_a_value_object_to_jsonb() -> None:
    (ddl,) = _statements(tph_family_with_a_value_object())
    assert "meta jsonb" in ddl


def test_provisioning_tpcs_maps_a_value_object_to_jsonb() -> None:
    (ddl,) = _statements(tpcs_family_with_a_value_object())
    assert "meta jsonb" in ddl


def test_provisioning_enforces_a_unique_secondary_index_as_its_own_statement() -> None:
    # The m-db-error uniqueViolation-via-secondary-index triggers (m-db-error-002/-008)
    # need the declared unique index on Tag.name enforced. It is a named statement of
    # its own rather than an inline constraint, so a violation reports a name a
    # rollout can correlate; the derived primary-key Index stays inline as the key
    # and gets no second object over the same columns.
    delta = _delta(_MODELS["error-cases"])
    (created,) = [
        index
        for index in delta.created_indices
        if index.logical_index_identity.name == "tag_name_uq"
    ]
    assert created.unique and created.physical_table.name == "tag"
    (statement,) = [text for text in delta.statements if text.startswith("create unique index ")]
    assert statement == (f"create unique index {created.physical_index_name.value} on tag (name)")
    assert "unique" not in _tables(_MODELS["error-cases"])["widget"]


def test_provisioning_emits_the_milestone_key_only_as_the_primary_key() -> None:
    # A temporal model authors no primary-key index; the derived one becomes
    # `primary key (...)` and is never also created as an Index of its own.
    delta = _delta(_MODELS["balance"])
    assert "unique" not in _tables(_MODELS["balance"])["balance"]
    assert not [text for text in delta.statements if text.startswith("create unique index ")]


def test_provisioning_tph_surfaces_a_descendant_declared_value_object_and_index() -> None:
    # `meta` and the unique index over `code` are declared ONLY on the
    # concrete subtype `Leaf`, never the root — invisible from `root.
    # value_objects` / `_unique_constraints((root,), ...)` alone; the shared
    # table's DDL must still carry both.
    model = tph_family_with_a_descendant_declared_value_object_and_index()
    assert "meta jsonb" in _tables(model)["root_tbl"]
    (created,) = _delta(model).created_indices
    assert created.logical_index_identity.name == "leaf_code_uq"
    assert created.physical_table.name == "root_tbl"


def test_provisioning_tpcs_surfaces_a_root_declared_unique_index() -> None:
    # `code` is declared only on the ROOT, and the index that constrains it is
    # ALSO declared only on the root — invisible from the concrete descriptor
    # alone; the concrete's own generated table must still enforce it.
    model = tpcs_family_with_a_root_declared_unique_index()
    (created,) = _delta(model).created_indices
    assert created.logical_index_identity.name == "root_code_uq"
    assert created.physical_table.name == "leaf"


def test_provisioning_tpcs_key_comes_from_the_tableless_root_derived_index() -> None:
    # The tableless root declares both the key and the axes, so it is the Entity
    # that derives the Index; the concrete table it maps carries those components
    # as its `primary key (...)` and no `unique (...)` beside it.
    delta = _delta(tpcs_family_with_a_temporal_root())
    (ddl,) = delta.statements
    assert "primary key (id, out_z)" in ddl
    assert "unique" not in ddl
    assert delta.created_indices == ()


def test_provisioning_creates_every_unique_index_over_one_column() -> None:
    delta = _delta(entity_with_two_indices_over_one_column())
    assert [index.logical_index_identity.name for index in delta.created_indices] == [
        "widget_code_uq",
        "widget_code_uq_dup",
    ]
    # Two definitions over the same column are two distinct physical objects, so
    # they take two distinct names rather than one collapsing into the other.
    names = {index.physical_index_name for index in delta.created_indices}
    assert len(names) == 2


def test_an_index_naming_an_undeclared_attribute_never_reaches_provisioning() -> None:
    # An accepted model's every Index names a declared Attribute (the resolver's
    # `metamodel-index-attribute-missing`), so provisioning's own unresolvable-
    # column guard is unreachable defensive code — the defect is caught before a
    # model can form.
    broken = dataclasses.replace(
        _RECORDS["error-cases"],
        entities=tuple(
            dataclasses.replace(
                entity,
                indices=(dataclasses.replace(entity.indices[0], attributes=("noSuchAttr",)),),
            )
            if entity.name == "Tag"
            else entity
            for entity in _RECORDS["error-cases"].entities
        ),
    )
    with pytest.raises(MetamodelValidationError, match="metamodel-index-attribute"):
        formed(
            dataclasses.replace(
                broken, entities=(next(e for e in broken.entities if e.name == "Tag"),)
            )
        )


# --------------------------------------------------------------------------- #
# What the generator itself owns: the shape of the whole answer, the refusal    #
# it aggregates, and what the returned value is allowed to keep alive.          #
# --------------------------------------------------------------------------- #
def test_equal_endpoints_produce_an_empty_delta() -> None:
    # An empty Unilateral Evolution asks for nothing, so the answer is a delta
    # with no statement rather than an absent one.
    evolution = evolve(_MODELS["grade"], _MODELS["grade"])
    assert isinstance(evolution, UnilateralEvolution)
    assert schema_delta(evolution, POSTGRES) == SchemaDelta(statements=(), created_indices=())


def test_no_statement_is_idempotent() -> None:
    # A delta states what must happen to a database at the earlier edition, so
    # nothing it emits reconciles an unknown one.
    for model in (_MODELS["error-cases"], _MODELS["storage-layout"], _DOCUMENT):
        for statement in _statements(model):
            assert "if exists" not in statement
            assert "if not exists" not in statement


@dataclasses.dataclass(frozen=True, slots=True)
class _RefusingIndexes(Dialect):
    """A Dialect that renders tables and refuses every Index."""

    def create_index(
        self,
        table: str,
        name: PhysicalIndexName,
        columns: Sequence[IndexColumnDdl],
        *,
        unique: bool,
    ) -> str | Unsupported:
        del table, name, columns, unique
        return Unsupported("this dialect indexes nothing")


def _refusing() -> Dialect:
    return _RefusingIndexes(
        name="refusing",
        reserved=POSTGRES.reserved,
        quote_char=POSTGRES.quote_char,
        error_codes=POSTGRES.error_codes,
        max_identifier_bytes=POSTGRES.max_identifier_bytes,
    )


def test_every_operation_a_dialect_refuses_is_reported_at_once() -> None:
    # No partial delta escapes: the whole plan is rendered and inspected before
    # anything is returned, so both refusals arrive in one error rather than the
    # first one arriving alone.
    model = entity_with_two_indices_over_one_column()
    with pytest.raises(UnsupportedSchemaEvolutionError) as raised:
        schema_delta(evolve(ABSENT, model), _refusing())
    error = raised.value
    assert error.dialect_identity == "refusing"
    assert [operation.kind for operation in error.operations] == ["CreateIndex", "CreateIndex"]
    assert {operation.location.table.name for operation in error.operations} == {"widget"}
    assert all(operation.reason == "this dialect indexes nothing" for operation in error.operations)
    # Each refusal names the model-altitude operations that asked for it.
    for operation in error.operations:
        assert operation.caused_by
        assert operation.location.index is not None


def _reachable(root: object) -> Iterator[object]:
    """Every VALUE reachable from ``root`` through the collector's own view.

    Classes and modules are not followed: every instance refers to its own type,
    and a type reaches its defining module's globals, so following one would make
    the whole interpreter reachable from anything.
    """
    seen = {id(root)}
    pending = [root]
    while pending:
        current = pending.pop()
        yield current
        for referent in gc.get_referents(current):
            if isinstance(referent, (type, ModuleType)) or id(referent) in seen:
                continue
            seen.add(id(referent))
            pending.append(referent)


def test_a_delta_retains_neither_the_model_nor_the_layouts_it_resolved() -> None:
    # A delta holds strings and created-Index records. Retaining the Metamodel or
    # a layout slot would keep a structure proportional to the model alive for as
    # long as a caller holds the statements, which is the shape this repository
    # has had to restore by hand before.
    model = _MODELS["error-cases"]
    delta = schema_delta(evolve(ABSENT, model), POSTGRES)
    held = list(_reachable(delta))
    assert delta.statements and delta.created_indices
    assert not any(item is model for item in held)
    assert not any(isinstance(item, ColumnSlot) for item in held)


# --------------------------------------------------------------------------- #
# The algebra is CLOSED by ADR 0063 and by the case schema's operation enum, so #
# every arm renders and addresses a location today even though the lowering     #
# reaches only two of them so far. An arm defined but unrendered would be a     #
# hole no type checker can see.                                                 #
# --------------------------------------------------------------------------- #
_TABLE = Table(name="widget")
_LABEL = PhysicalColumn(Column(name="label"), STRING, 8, nullable=False)
_WIDER = PhysicalColumn(Column(name="label"), STRING, 16, nullable=True)
_INDEX = IndexDefinition(
    table=_TABLE,
    index=IndexIdentity(EntityIdentity(namespace="parallax.test", name="Widget"), "widget_label"),
    components=(AttributeIdentity(EntityIdentity("parallax.test", "Widget"), "label"),),
    columns=(_LABEL,),
    unique=True,
)
_NAME = PhysicalIndexName("pxi_widget_label_0")


def test_adding_a_column_renders_and_addresses_that_column() -> None:
    operation = AddColumn(table=_TABLE, column=_WIDER, caused_by=())
    assert render(operation, POSTGRES) == "alter table widget add column label varchar(16)"
    assert member_key(operation) == "label"
    assert location_of(operation) == PhysicalLocation(table=_TABLE, column=Column(name="label"))


def test_expanding_a_column_renders_the_whole_widening_and_addresses_the_later_column() -> None:
    operation = ExpandColumnDomain(table=_TABLE, earlier=_LABEL, later=_WIDER, caused_by=())
    assert render(operation, POSTGRES) == (
        "alter table widget alter column label type varchar(16), alter column label drop not null"
    )
    assert member_key(operation) == "label"
    assert location_of(operation) == PhysicalLocation(table=_TABLE, column=Column(name="label"))


def test_dropping_an_index_renders_and_addresses_its_physical_name() -> None:
    operation = DropIndex(definition=_INDEX, name=_NAME, caused_by=())
    assert render(operation, POSTGRES) == "drop index pxi_widget_label_0"
    assert member_key(operation) == _NAME.value
    assert location_of(operation) == PhysicalLocation(table=_TABLE, index=_NAME)


def test_creating_an_index_addresses_its_physical_name() -> None:
    operation = CreateIndex(definition=_INDEX, name=_NAME, caused_by=())
    assert render(operation, POSTGRES) == (
        "create unique index pxi_widget_label_0 on widget (label)"
    )
    assert member_key(operation) == _NAME.value
    assert location_of(operation) == PhysicalLocation(table=_TABLE, index=_NAME)


def test_creating_a_table_addresses_no_member() -> None:
    operation = CreateTable(
        table=_TABLE, columns=(_LABEL,), primary_key=(Column(name="label"),), caused_by=()
    )
    assert member_key(operation) == ""
    assert location_of(operation) == PhysicalLocation(table=_TABLE)
