"""Independent immutable Storage Layout compiler and validation contract."""

from __future__ import annotations

import ast
import dataclasses
import enum
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import Any, NamedTuple, cast

import pytest

import reference_harness._statement_bind_inference as statement_bind_inference
import reference_harness.case_preflight as case_preflight
import reference_harness.case_runner as case_runner
import reference_harness.ddl_builder as ddl_builder
import reference_harness.object_query_oracle as object_query_oracle
import reference_harness.storage_layout as storage_layout
import reference_harness.unit_work_scenario as unit_work_scenario
import reference_harness.write_plan as write_plan
from reference_harness.case import Model, load_model
from reference_harness.data_loader import load_model as load_fixture_rows
from reference_harness.ddl_builder import ddl_for
from reference_harness.storage_layout import (
    STORAGE_LAYOUT_COLUMN_COLLISION,
    STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE,
    STORAGE_LAYOUT_INDEX_OVER_DOCUMENT_MEMBER,
    STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
    AttributeContributor,
    ColumnTier,
    DirectColumn,
    DocumentMember,
    DocumentPath,
    EntityDocument,
    InheritanceDiscriminator,
    MemberAddress,
    RelationalDocument,
    ValueObjectContributor,
    _interned,
    _interned_ordinal_selection,
    compile_storage_layout,
    validate_storage_layout,
)
from reference_harness.temporality import derive_temporal_structure
from reference_harness.unit_work_scenario.reads import ScenarioReads
from reference_harness.value_object_resolve import RejectionError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPATIBILITY_ROOT = _REPO_ROOT / "core" / "compatibility"


class _RecordingProvider:
    """A no-database provider recording the fixture-load calls it receives."""

    dialect = "postgres"

    def __init__(self) -> None:
        self.loads: list[tuple[str, list[str], list[list[Any]]]] = []

    def load(self, table: str, columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.loads.append((table, list(columns), [list(row) for row in rows]))


def _storage_layout_model() -> Model:
    return load_model(_COMPATIBILITY_ROOT, "models/storage-layout.yaml")


def _create_table_ddl(model: Model, table: str, dialect: str = "postgres") -> str:
    prefix = f"create table {table} ("
    (statement,) = [ddl for ddl in ddl_for(model, dialect) if ddl.startswith(prefix)]
    return statement


def _ddl_column(statement: str, column: str) -> str:
    (line,) = [
        stripped
        for raw in statement.splitlines()
        if (stripped := raw.strip().rstrip(",")).split(" ")[0] == column
    ]
    return line


class _VisitedDefinitions(list[dict[str, Any]]):
    def __init__(self, values: list[dict[str, Any]]) -> None:
        super().__init__(values)
        self.visits = 0

    def __iter__(self) -> Iterator[dict[str, Any]]:
        for definition in super().__iter__():
            self.visits += 1
            yield definition


def _retained_size(value: object) -> int:
    seen: set[int] = set()

    def measure(current: object) -> int:
        if id(current) in seen:
            return 0
        seen.add(id(current))
        size = sys.getsizeof(current)
        if isinstance(current, enum.Enum):
            return size
        if dataclasses.is_dataclass(current) and not isinstance(current, type):
            return size + sum(
                measure(getattr(current, field.name)) for field in dataclasses.fields(current)
            )
        if isinstance(current, Mapping):
            return size + sum(measure(key) + measure(item) for key, item in current.items())
        if isinstance(current, (tuple, list, set, frozenset)):
            return size + sum(measure(item) for item in current)
        slots = getattr(type(current), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        return size + sum(
            measure(getattr(current, slot))
            for slot in slots
            if isinstance(slot, str) and hasattr(current, slot)
        )

    return measure(value)


def _derived(definition: dict[str, Any]) -> dict[str, Any]:
    """``definition`` carrying the endpoint attributes its profile derives."""
    return derive_temporal_structure({"entity": definition})["entity"]


def _attribute(
    name: str,
    *,
    column: str | None = None,
    primary_key: bool = False,
    nullable: bool = False,
) -> dict[str, Any]:
    declaration: dict[str, Any] = {"name": name, "type": "int64"}
    if column is not None:
        declaration["column"] = column
    if primary_key:
        declaration["primaryKey"] = True
    if nullable:
        declaration["nullable"] = True
    return declaration


def _standalone_definition() -> dict[str, Any]:
    return _derived(
        {
            "name": "Record",
            "namespace": "example",
            "table": "record",
            "temporality": "transaction-time",
            "attributes": [
                _attribute("id", primary_key=True),
                _attribute("label"),
                _attribute("revisedBy"),
            ],
            "valueObjects": [{"name": "payload", "column": "payload_doc"}],
        }
    )


def _tph_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "Record",
            "namespace": "example",
            "table": "record",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [
                _attribute("id", primary_key=True),
                _attribute("label"),
            ],
        },
        {
            "name": "AlphaRecord",
            "namespace": "example",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "Record",
                "tagValue": "alpha",
            },
            "attributes": [_attribute("alphaValue")],
            "valueObjects": [{"name": "payload", "column": "payload_doc"}],
        },
        {
            "name": "BetaRecord",
            "namespace": "example",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "Record",
                "tagValue": "beta",
            },
            "attributes": [_attribute("betaValue")],
        },
    ]


def _tpcs_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "Document",
            "namespace": "example",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-concrete-subtype",
            },
            "attributes": [
                _attribute("id", primary_key=True),
                _attribute("title"),
            ],
        },
        {
            "name": "Invoice",
            "namespace": "example",
            "table": "invoice",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "Document",
            },
            "attributes": [_attribute("invoiceDetail", column="detail")],
        },
        {
            "name": "Memo",
            "namespace": "example",
            "table": "memo",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": "Document",
            },
            "attributes": [_attribute("memoDetail", column="detail")],
        },
    ]


def _ranked_temporal_definitions(mapping: str) -> tuple[list[dict[str, Any]], str, str]:
    root = f"example.{mapping.title()}Temporal"
    local_root = root.rpartition(".")[2]
    concrete = f"example.{mapping.title()}TemporalRow"
    root_definition: dict[str, Any] = _derived(
        {
            "name": local_root,
            "namespace": "example",
            "temporality": "bitemporal",
            "attributes": [_attribute("id", primary_key=True)],
        }
    )
    if mapping == "standalone":
        table = "standalone_temporal"
        root_definition["table"] = table
        return [root_definition], table, root
    if mapping == "tph":
        table = "tph_temporal"
        root_definition["table"] = table
        root_definition["inheritance"] = {
            "role": "root",
            "strategy": "table-per-hierarchy",
            "tag": {"column": "kind"},
        }
        return (
            [
                root_definition,
                {
                    "name": concrete.rpartition(".")[2],
                    "namespace": "example",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": local_root,
                        "tagValue": "row",
                    },
                    "attributes": [],
                },
            ],
            table,
            root,
        )
    table = "tpcs_temporal"
    root_definition["inheritance"] = {
        "role": "root",
        "strategy": "table-per-concrete-subtype",
    }
    return (
        [
            root_definition,
            {
                "name": concrete.rpartition(".")[2],
                "namespace": "example",
                "table": table,
                "inheritance": {"role": "concrete-subtype", "parent": local_root},
                "attributes": [],
            },
        ],
        table,
        root,
    )


def _large_tph_definitions(width: int) -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = [
        {
            "name": f"WideRoot{width}",
            "table": f"wide_tph_{width}",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [
                _attribute("id", primary_key=True),
                *(_attribute(f"shared{index}") for index in range(width)),
            ],
        }
    ]
    definitions.extend(
        {
            "name": f"WideConcrete{width}_{index}",
            "inheritance": {
                "role": "concrete-subtype",
                "parent": f"WideRoot{width}",
                "tagValue": f"row-{index}",
            },
            "attributes": [_attribute(f"local{index}")],
        }
        for index in range(width)
    )
    return definitions


def _mapping_owner(category: str, prefix: str, table: str) -> tuple[list[dict[str, Any]], str]:
    owner = f"{prefix}Owner"
    if category == "standalone":
        return [
            {
                "name": owner,
                "table": table,
                "attributes": [_attribute("id", primary_key=True)],
            }
        ], owner
    if category == "tph":
        return [
            {
                "name": owner,
                "table": table,
                "inheritance": {
                    "role": "root",
                    "strategy": "table-per-hierarchy",
                    "tag": {"column": "kind"},
                },
                "attributes": [_attribute("id", primary_key=True)],
            },
            {
                "name": f"{prefix}Row",
                "inheritance": {
                    "role": "concrete-subtype",
                    "parent": owner,
                    "tagValue": prefix.lower(),
                },
                "attributes": [],
            },
        ], owner
    root = f"{prefix}Root"
    return [
        {
            "name": root,
            "inheritance": {
                "role": "root",
                "strategy": "table-per-concrete-subtype",
            },
            "attributes": [_attribute("id", primary_key=True)],
        },
        {
            "name": owner,
            "table": table,
            "inheritance": {"role": "concrete-subtype", "parent": root},
            "attributes": [],
        },
    ], owner


def test_standalone_layout_has_table_wide_tiers_provenance_and_physical_key() -> None:
    definition = _standalone_definition()
    facet = compile_storage_layout([definition])
    layout = facet.table("record")
    assert layout is not None
    assert [slot.column for slot in layout.columns] == [
        "id",
        "label",
        "revised_by",
        "in_z",
        "out_z",
        "payload_doc",
    ]
    assert [slot.tier for slot in layout.columns] == [
        ColumnTier.IDENTITY,
        ColumnTier.DOMAIN,
        ColumnTier.DOMAIN,
        ColumnTier.TEMPORAL,
        ColumnTier.TEMPORAL,
        ColumnTier.DOCUMENT,
    ]
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeContributor("example.Record", "id"),
        AttributeContributor("example.Record", "txEnd"),
    ]
    assert [layout.columns.index(slot) for slot in layout.physical_primary_key] == [0, 4]
    payload = layout.contribution(ValueObjectContributor("example.Record", "payload"))
    assert payload is not None
    assert payload.declaring_owner == "example.Record"
    assert payload.applicable_entities == frozenset({"example.Record"})


@pytest.mark.parametrize("mapping", ["standalone", "tph", "tpcs"])
def test_physical_key_temporal_ends_follow_dimension_rank(mapping: str) -> None:
    definitions, table, root = _ranked_temporal_definitions(mapping)
    layout = compile_storage_layout(definitions).table(table)
    assert layout is not None
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeContributor(root, "id"),
        AttributeContributor(root, "validEnd"),
        AttributeContributor(root, "txEnd"),
    ]


def test_an_independently_constructed_equal_slot_matches_by_structure() -> None:
    layout = compile_storage_layout([_standalone_definition()]).tables[0]
    slot = layout.contribution(AttributeContributor("example.Record", "label"))
    assert slot is not None
    equal = type(slot)(
        column=str(slot.column),
        tier=slot.tier,
        contributor=AttributeContributor("example.Record", "label"),
        declaring_owner=str(slot.declaring_owner),
        effective_nullable=slot.effective_nullable,
        applicable_entities=frozenset(str(entity) for entity in slot.applicable_entities),
    )
    assert equal == slot
    assert layout.columns.index(equal) == layout.columns.index(slot)


def test_audit_classifier_covers_all_six_tiers_and_deduplicates_temporal_alias() -> None:
    definition = _standalone_definition()
    audit = AttributeContributor("example.Record", "revisedBy")
    tx_start = AttributeContributor("example.Record", "txStart")
    facet = compile_storage_layout([definition], audit_designations=frozenset({audit, tx_start}))
    layout = facet.table("record")
    assert layout is not None
    assert [slot.tier for slot in layout.columns] == [
        ColumnTier.IDENTITY,
        ColumnTier.DOMAIN,
        ColumnTier.TEMPORAL,
        ColumnTier.TEMPORAL,
        ColumnTier.AUDIT,
        ColumnTier.DOCUMENT,
    ]
    matches = [slot for slot in layout.columns if slot.contributor == tx_start]
    assert len(matches) == 1
    assert matches[0].tier is ColumnTier.TEMPORAL


def test_tph_layout_accumulates_applicability_and_effective_nullability() -> None:
    facet = compile_storage_layout(_tph_definitions())
    assert [layout.table for layout in facet.tables] == ["record"]
    layout = facet.tables[0]
    root = "example.Record"
    alpha = "example.AlphaRecord"
    beta = "example.BetaRecord"
    root_slot = layout.contribution(AttributeContributor(root, "label"))
    alpha_slot = layout.contribution(AttributeContributor(alpha, "alphaValue"))
    discriminator = layout.contribution(InheritanceDiscriminator(root))
    document = layout.contribution(ValueObjectContributor(alpha, "payload"))
    assert root_slot is not None
    assert alpha_slot is not None
    assert discriminator is not None
    assert document is not None
    assert root_slot.applicable_entities == frozenset({alpha, beta})
    assert not root_slot.effective_nullable
    assert alpha_slot.applicable_entities == frozenset({alpha})
    assert alpha_slot.effective_nullable
    assert discriminator.applicable_entities == frozenset({alpha, beta})
    assert not discriminator.effective_nullable
    assert document.effective_nullable


def _customer_layout() -> Any:
    model = load_model(_COMPATIBILITY_ROOT, "models/customer.yaml")
    layout = compile_storage_layout(model.entity_defs).table("customer")
    assert layout is not None
    return layout


def test_placement_and_contribution_agree_for_every_conventional_top_level_member() -> None:
    # Under `Columns` every top-level member is placed over the slot its own
    # contributor owns, so the two lookups are one contract's two questions
    # rather than two spellings of one answer.
    layout = _customer_layout()
    customer = "parallax.compatibility.Customer"
    for member, contributor in (
        (MemberAddress(customer, ("id",)), AttributeContributor(customer, "id")),
        (MemberAddress(customer, ("name",)), AttributeContributor(customer, "name")),
        (MemberAddress(customer, ("address",)), ValueObjectContributor(customer, "address")),
    ):
        assert layout.placement(member) == DirectColumn(layout.contribution(contributor))


def test_a_conventional_value_object_leaf_is_placed_inside_its_own_structured_column() -> None:
    # Conventional storage already has Document Paths: a leaf's path begins at the
    # first segment below the occurrence, over that occurrence's own column, which
    # is the location conventional nested access already reads.
    layout = _customer_layout()
    customer = "parallax.compatibility.Customer"
    address = layout.contribution(ValueObjectContributor(customer, "address"))
    assert layout.placement(MemberAddress(customer, ("address", "city"))) == DocumentPath(
        address, ("city",)
    )
    assert layout.placement(
        MemberAddress(customer, ("address", "geo", "point", "lat"))
    ) == DocumentPath(address, ("geo", "point", "lat"))
    assert layout.placement(
        MemberAddress(customer, ("address", "phones", "number"))
    ) == DocumentPath(address, ("phones", "number"))
    assert layout.placement(MemberAddress(customer, ("address", "absent"))) is None


def test_a_document_layout_contributes_one_shared_not_null_structured_column_last() -> None:
    definitions = _document_hierarchy()
    layout = compile_storage_layout(definitions).table("record")
    assert layout is not None
    assert [slot.column for slot in layout.columns] == ["id", "kind", "doc"]
    structured = layout.columns[-1]
    assert structured.contributor == RelationalDocument("example.Record")
    assert structured.tier is ColumnTier.DOCUMENT
    assert structured.declaring_owner == "example.Record"
    assert not structured.effective_nullable
    assert structured.applicable_entities == frozenset(
        {"example.AlphaRecord", "example.BetaRecord"}
    )


def test_document_resident_members_are_placed_at_one_segment_under_the_shared_column() -> None:
    definitions = _document_hierarchy()
    layout = compile_storage_layout(definitions).table("record")
    assert layout is not None
    structured = layout.columns[-1]
    root = "example.Record"
    alpha = "example.AlphaRecord"
    assert layout.placement(MemberAddress(root, ("id",))) == DirectColumn(
        layout.contribution(AttributeContributor(root, "id"))
    )
    assert layout.placement(MemberAddress(root, ("label",))) == DocumentPath(structured, ("label",))
    assert layout.placement(MemberAddress(alpha, ("payload",))) == DocumentPath(
        structured, ("payload",)
    )
    assert layout.contribution(ValueObjectContributor(alpha, "payload")) is None


def test_an_entity_document_carries_the_members_its_own_ancestry_placed_inside() -> None:
    facet = compile_storage_layout(_document_hierarchy())
    root = "example.Record"
    alpha = "example.AlphaRecord"
    document = facet.document(alpha)
    assert document.column == "doc"
    # Inherited members first, in ancestry declaration order, then the occurrences;
    # a leaf carries the declared type its stored spelling decodes through and an
    # occurrence carries none. The primary key and the tag never appear: one is
    # placed in a Column of its own and the other is no declared member at all.
    assert document.members == (
        DocumentMember(MemberAddress(root, ("label",)), "label", ("label",), "int64"),
        DocumentMember(
            MemberAddress(alpha, ("alphaValue",)), "alpha_value", ("alphaValue",), "int64"
        ),
        DocumentMember(MemberAddress(alpha, ("payload",)), "payload", ("payload",), None),
    )
    assert [member.name for member in document.members] == ["label", "alphaValue", "payload"]
    # Disjoint siblings share the Table and the Column, never each other's members.
    assert [member.name for member in facet.document("example.BetaRecord").members] == [
        "label",
        "betaValue",
    ]


def test_a_rowless_position_answers_for_the_structured_column_its_family_shares() -> None:
    # A table-per-hierarchy root owns no rows and so has no layout selection, but it
    # does map to the shared Table, and a read of that position asks the same
    # residence question a read of one of its subtypes does.
    facet = compile_storage_layout(_document_hierarchy())
    root = "example.Record"
    assert facet.entity(root) is None
    assert facet.document(root).column == "doc"
    assert [member.name for member in facet.document(root).members] == ["label"]


def test_an_entity_outside_a_relational_document_layout_answers_the_empty_document() -> None:
    # A tableless table-per-concrete-subtype root, a conventional ``Columns``
    # entity, and a name no definition claims all answer alike, which is what lets
    # a consumer's document fan-out stay unconditional.
    assert compile_storage_layout(_document_tpcs()).document("example.Document") == EntityDocument(
        "", ()
    )
    facet = compile_storage_layout(_tph_definitions())
    assert facet.document("example.AlphaRecord") == EntityDocument("", ())
    assert facet.document("example.Absent") == EntityDocument("", ())


def test_every_corpus_document_member_is_the_placement_the_layout_compiled() -> None:
    checked = 0
    for model_path in sorted(_COMPATIBILITY_ROOT.glob("models/**/*.yaml")):
        model = load_model(_COMPATIBILITY_ROOT, model_path.relative_to(_COMPATIBILITY_ROOT))
        facet = model.storage_layout
        for entity in model.entities:
            document = facet.document(entity.canonical_name)
            layout = facet.table(entity.table) if entity.table else None
            if not document.column:
                continue
            assert layout is not None
            slot = layout.column(document.column)
            assert slot is not None
            assert isinstance(slot.contributor, RelationalDocument)
            for member in document.members:
                assert layout.placement(member.address) == DocumentPath(slot, member.path)
                assert layout.column(member.column) is None
                checked += 1
    assert checked


def test_a_tpcs_family_receives_one_structured_column_per_concrete_table() -> None:
    # One root declares one layout policy and one Structured Column name that
    # every concrete Table in the family receives.
    definitions = _tpcs_definitions()
    definitions[0]["layout"] = {"document": {"column": "doc"}}
    definitions[1]["attributes"] = [_attribute("invoiceDetail")]
    definitions[2]["attributes"] = [_attribute("memoDetail")]
    facet = compile_storage_layout(definitions)
    root = "example.Document"
    for table, owner, detail in (
        ("invoice", "example.Invoice", "invoiceDetail"),
        ("memo", "example.Memo", "memoDetail"),
    ):
        layout = facet.table(table)
        assert layout is not None
        assert [slot.column for slot in layout.columns] == ["id", "doc"]
        structured = layout.contribution(RelationalDocument(root))
        assert structured is not None
        assert layout.placement(MemberAddress(root, ("title",))) == DocumentPath(
            structured, ("title",)
        )
        assert layout.placement(MemberAddress(owner, (detail,))) == DocumentPath(
            structured, (detail,)
        )


def test_branch_placements_align_with_the_positions_logical_member_union() -> None:
    facet = compile_storage_layout(_tph_definitions())
    view = facet.position(("example.AlphaRecord", "example.BetaRecord"))
    assert view is not None
    root = "example.Record"
    alpha = "example.AlphaRecord"
    beta = "example.BetaRecord"
    assert view.members == (
        MemberAddress(root, ("id",)),
        MemberAddress(root, ("label",)),
        MemberAddress(alpha, ("alphaValue",)),
        MemberAddress(beta, ("betaValue",)),
        MemberAddress(alpha, ("payload",)),
    )
    (branch,) = view.branches
    assert len(branch.placements) == len(view.members)
    assert branch.placements == tuple(branch.layout.placement(member) for member in view.members)


def test_private_applicability_intern_deduplicates_structurally_equal_keys() -> None:
    intern: dict[frozenset[str], frozenset[str]] = {}
    first = _interned({"example.Alpha", "example.Beta"}, intern)
    second = _interned({"example.Beta", "example.Alpha"}, intern)
    assert first == second
    assert len(intern) == 1


def test_private_entity_slot_selections_are_compact_and_interned_by_ordinals() -> None:
    facet = compile_storage_layout(_tph_definitions())
    layout = facet.tables[0]
    intern: dict[int, Any] = {}
    first = _interned_ordinal_selection(layout, "example.AlphaRecord", intern)
    second = _interned_ordinal_selection(layout, "example.AlphaRecord", intern)
    view = facet.entity("example.AlphaRecord")
    assert view is not None
    assert first == second
    assert len(intern) == 1
    assert first.materialize(layout.columns) == view.columns


def test_rowless_tph_branch_still_contributes_to_the_complete_shared_layout() -> None:
    definitions = _tph_definitions()
    definitions.append(
        {
            "name": "DormantRecord",
            "namespace": "example",
            "inheritance": {
                "role": "abstract-subtype",
                "parent": "Record",
            },
            "attributes": [_attribute("dormantValue")],
        }
    )
    facet = compile_storage_layout(definitions)
    layout = facet.tables[0]
    dormant = layout.contribution(AttributeContributor("example.DormantRecord", "dormantValue"))
    assert dormant is not None
    assert dormant.applicable_entities == frozenset()
    assert dormant.effective_nullable
    alpha = facet.entity("example.AlphaRecord")
    assert alpha is not None
    assert dormant not in alpha.columns


def test_tph_entity_and_position_views_reference_existing_slots() -> None:
    facet = compile_storage_layout(_tph_definitions())
    root = "example.Record"
    alpha = "example.AlphaRecord"
    beta = "example.BetaRecord"
    alpha_view = facet.entity(alpha)
    beta_view = facet.entity(beta)
    assert alpha_view is not None
    assert beta_view is not None
    assert alpha_view.layout == beta_view.layout
    assert alpha_view.discriminator is not None
    assert alpha_view.discriminator.value == "alpha"
    assert alpha_view.discriminator.slot == alpha_view.layout.contribution(
        InheritanceDiscriminator(root)
    )
    assert facet.entity(root) is None
    position = facet.position((alpha,))
    assert position is not None
    assert len(position.branches) == 1
    assert position.branches[0].discriminator_slot == alpha_view.discriminator.slot
    assert AttributeContributor(beta, "betaValue") not in {
        column.contributor for column in position.columns
    }


def test_tpcs_layouts_and_position_preserve_branch_slot_absence() -> None:
    facet = compile_storage_layout(_tpcs_definitions())
    root = "example.Document"
    invoice = "example.Invoice"
    memo = "example.Memo"
    assert [layout.table for layout in facet.tables] == ["invoice", "memo"]
    for layout in facet.tables:
        assert [slot.column for slot in layout.columns] == ["id", "title", "detail"]
    invoice_key = facet.tables[0].contribution(AttributeContributor(root, "id"))
    memo_key = facet.tables[1].contribution(AttributeContributor(root, "id"))
    assert invoice_key is not None
    assert memo_key is not None
    assert invoice_key != memo_key
    position = facet.position((invoice, memo))
    assert position is not None
    assert [column.contributor for column in position.columns] == [
        AttributeContributor(root, "id"),
        AttributeContributor(root, "title"),
        AttributeContributor(invoice, "invoiceDetail"),
        AttributeContributor(memo, "memoDetail"),
    ]
    assert [branch.layout.table for branch in position.branches] == ["invoice", "memo"]
    assert [slot is not None for slot in position.branches[0].slots] == [
        True,
        True,
        True,
        False,
    ]
    assert [slot is not None for slot in position.branches[1].slots] == [
        True,
        True,
        False,
        True,
    ]


def test_mapping_owner_collision_uses_canonical_first_owner_before_columns() -> None:
    definitions = [
        {
            "name": "Third",
            "table": "shared",
            "attributes": [_attribute("thirdId", primary_key=True)],
        },
        {
            "name": "Second",
            "table": "shared",
            "attributes": [
                _attribute("secondId", primary_key=True),
                _attribute("duplicate", column="second_id"),
            ],
        },
        {
            "name": "First",
            "table": "shared",
            "attributes": [_attribute("firstId", primary_key=True)],
        },
    ]
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout(definitions)
    assert caught.value.rule == STORAGE_LAYOUT_TABLE_MAPPING_COLLISION
    assert "'First' and 'Second'" in caught.value.detail


def test_mapping_collision_rejects_before_an_earlier_unique_table_column_collision() -> None:
    definitions = [
        {
            "name": "AColumnOwner",
            "table": "column_collision",
            "attributes": [
                _attribute("id", primary_key=True),
                _attribute("value"),
            ],
            "valueObjects": [{"name": "payload", "column": "value"}],
        },
        {
            "name": "BFirstTableOwner",
            "table": "mapping_collision",
            "attributes": [_attribute("id", primary_key=True)],
        },
        {
            "name": "CSecondTableOwner",
            "table": "mapping_collision",
            "attributes": [_attribute("id", primary_key=True)],
        },
    ]
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout(definitions)
    assert caught.value.rule == STORAGE_LAYOUT_TABLE_MAPPING_COLLISION
    assert "'BFirstTableOwner' and 'CSecondTableOwner'" in caught.value.detail


def test_interleaved_two_table_collisions_reject_the_first_later_owner_in_canonical_order() -> None:
    definitions = [
        {
            "name": "DLaterA",
            "table": "table_a",
            "attributes": [_attribute("id", primary_key=True)],
        },
        {
            "name": "BFirst",
            "table": "table_b",
            "attributes": [_attribute("id", primary_key=True)],
        },
        {
            "name": "CLaterB",
            "table": "table_b",
            "attributes": [_attribute("id", primary_key=True)],
        },
        {
            "name": "AFirst",
            "table": "table_a",
            "attributes": [_attribute("id", primary_key=True)],
        },
    ]
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout(definitions)
    assert caught.value.rule == STORAGE_LAYOUT_TABLE_MAPPING_COLLISION
    assert "'BFirst' and 'CLaterB'" in caught.value.detail


@pytest.mark.parametrize(
    ("first_category", "later_category"),
    [
        ("standalone", "tph"),
        ("tph", "tpcs"),
        ("tpcs", "standalone"),
    ],
)
def test_cross_category_mapping_owners_share_one_table_claim_stream(
    first_category: str, later_category: str
) -> None:
    first, first_owner = _mapping_owner(first_category, "A", "shared")
    later, later_owner = _mapping_owner(later_category, "B", "shared")
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout([*later, *first])
    assert caught.value.rule == STORAGE_LAYOUT_TABLE_MAPPING_COLLISION
    assert f"'{first_owner}' and '{later_owner}'" in caught.value.detail


def test_column_collision_uses_category_order_and_distinct_provenance() -> None:
    definition = {
        "name": "Record",
        "table": "record",
        "inheritance": {
            "role": "root",
            "strategy": "table-per-hierarchy",
            "tag": {"column": "kind"},
        },
        "attributes": [
            _attribute("id", primary_key=True),
            _attribute("kind"),
        ],
    }
    concrete = {
        "name": "ConcreteRecord",
        "inheritance": {
            "role": "concrete-subtype",
            "parent": "Record",
            "tagValue": "record",
        },
        "attributes": [],
    }
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout([definition, concrete])
    assert caught.value.rule == STORAGE_LAYOUT_COLUMN_COLLISION
    assert "discriminator of Record" in caught.value.detail
    assert "Attribute Record.kind" in caught.value.detail


def _document_standalone(**overrides: Any) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "name": "Note",
        "table": "note",
        "layout": {"document": {"column": "payload"}},
        "attributes": [_attribute("id", primary_key=True)],
    }
    definition.update(overrides)
    return definition


def _document_tpcs() -> list[dict[str, Any]]:
    definitions = _tpcs_definitions()
    definitions[0]["layout"] = {"document": {"column": "doc"}}
    for definition in definitions[1:]:
        for attribute in definition["attributes"]:
            attribute.pop("column", None)
    return definitions


def test_a_temporal_document_tpcs_root_is_accepted() -> None:
    definitions = _document_tpcs()
    definitions[0]["temporality"] = "transaction-time"
    validate_storage_layout([_derived(definitions[0]), *definitions[1:]])


def test_a_standalone_document_layout_owner_is_accepted() -> None:
    # A well-formed standalone declaration is a supported root-owned Document layout
    # and therefore produces no Storage Layout issue.
    validate_storage_layout([_document_standalone()])


@pytest.mark.parametrize("temporality", ["transaction-time", "bitemporal"])
def test_a_temporal_document_layout_owner_is_accepted(temporality: str) -> None:
    # Transaction-Time and Valid-Time axes remain direct-role Columns, so either
    # temporal profile composes with a root-owned Document layout without issue.
    definition = _document_standalone()
    definition["temporality"] = temporality
    validate_storage_layout([_derived(definition)])


def _document_hierarchy() -> list[dict[str, Any]]:
    """A TPH family whose root selects Relational Document Layout.

    The subtype occurrence drops its Column Override, because a document-resident
    member may not carry one; the override is its own rejection, proven below.
    """
    definitions = _tph_definitions()
    definitions[0]["layout"] = {"document": {"column": "doc"}}
    definitions[1]["valueObjects"] = [{"name": "payload"}]
    return definitions


def test_a_document_tpcs_family_has_one_structured_column_per_branch() -> None:
    definitions = _document_tpcs()
    validate_storage_layout(definitions)
    layout = compile_storage_layout(definitions)
    for table in ("invoice", "memo"):
        branch = layout.table(table)
        assert branch is not None
        assert [slot.column for slot in branch.columns][-1] == "doc"


def test_a_document_tph_family_is_accepted() -> None:
    validate_storage_layout(_document_hierarchy())


def test_a_layout_declared_off_the_root_raises_nothing_in_storage_layout() -> None:
    # Root ownership comes from the group projection, so a descendant's own
    # declaration is invisible here: Inheritance reports
    # `inheritance-layout-not-root-owned` as the root-ownership defect.
    definitions = _tph_definitions()
    definitions[1]["layout"] = {"document": {"column": "payload"}}
    validate_storage_layout(definitions)


def test_a_document_column_collision_reports_the_physical_defect() -> None:
    # A Structured Column colliding with a direct-role Column is a physical layout
    # defect, so Storage Layout reports the collision at the later claim.
    definition = _document_standalone(layout={"document": {"column": "id"}})
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout([definition])
    assert caught.value.rule == STORAGE_LAYOUT_COLUMN_COLLISION
    assert "Structured Column of the layout Note declares" in caught.value.detail
    assert "Attribute Note.id" in caught.value.detail


def test_document_resident_members_claim_no_column_and_cannot_collide() -> None:
    # A spelling two members share collides under `Columns`; under `Document`
    # neither is a claimant at all, so what the model reports is the pair of
    # Column Overrides that contradict the layout.
    definition = _document_standalone(
        attributes=[
            _attribute("id", primary_key=True),
            _attribute("profileText", column="profile"),
        ],
        valueObjects=[{"name": "profileDocument", "column": "profile"}],
    )
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout([definition])
    assert caught.value.rule == STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE
    assert "Note.profileText" in caught.value.detail


def test_a_direct_role_attribute_may_still_override_its_column() -> None:
    # Role 1 stays a direct Column, so its override names a Column the member
    # really occupies and nothing refuses this model.
    definition = _document_standalone(
        attributes=[_attribute("id", column="note_key", primary_key=True)]
    )
    validate_storage_layout([definition])


def test_restating_a_document_resident_members_conventional_column_is_accepted() -> None:
    definition = _document_standalone(
        attributes=[
            _attribute("id", primary_key=True),
            _attribute("displayName", column="display_name"),
        ]
    )
    validate_storage_layout([definition])


def test_an_index_over_a_document_resident_attribute_is_refused() -> None:
    definition = _document_standalone(
        attributes=[_attribute("id", primary_key=True), _attribute("displayName")],
        indices=[{"name": "byDisplayName", "attributes": ["displayName"]}],
    )
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout([definition])
    assert caught.value.rule == STORAGE_LAYOUT_INDEX_OVER_DOCUMENT_MEMBER
    assert "byDisplayName" in caught.value.detail


def test_an_index_over_a_direct_role_attribute_still_resolves() -> None:
    definition = _document_standalone(
        attributes=[_attribute("id", primary_key=True)],
        indices=[{"name": "byKey", "attributes": ["id"]}],
    )
    validate_storage_layout([definition])


def _note_owning_a_holder(*, join_source: str = "ownerId") -> list[dict[str, Any]]:
    """A document-mapped `Note` joined to a conventional `Holder` on `ownerId`."""
    return [
        _document_standalone(
            attributes=[
                _attribute("id", primary_key=True),
                _attribute("ownerId", column="owner_key"),
            ],
            relationships=[
                {
                    "name": "owner",
                    "cardinality": "many-to-one",
                    "join": {
                        "source": join_source,
                        "target": {"entity": "Holder", "attribute": "id"},
                    },
                }
            ],
            indices=[{"name": "byOwner", "attributes": ["ownerId"]}],
        ),
        {"name": "Holder", "table": "holder", "attributes": [_attribute("id", primary_key=True)]},
    ]


def test_a_join_endpoint_stays_direct_so_neither_layout_rule_fires_on_it() -> None:
    # Role 2 comes from the validation-time join-endpoint projection, so
    # `ownerId` keeps its Column, its Override, and its Index.
    validate_storage_layout(_note_owning_a_holder())


def test_a_join_that_does_not_resolve_locally_designates_no_endpoint() -> None:
    # An endpoint of a join whose source names no Attribute of the declaring
    # Entity is excluded, so `ownerId` is document-resident here while
    # relationship formation rejects the join. Both are permitted, unordered.
    with pytest.raises(RejectionError) as caught:
        validate_storage_layout(_note_owning_a_holder(join_source="missing"))
    assert caught.value.rule == STORAGE_LAYOUT_DOCUMENT_MEMBER_COLUMN_OVERRIDE


def _document_family_joined_through_an_inherited_endpoint() -> list[dict[str, Any]]:
    return [
        {
            "name": "Ledger",
            "namespace": "example",
            "layout": {"document": {"column": "doc"}},
            "inheritance": {"role": "root", "strategy": "table-per-concrete-subtype"},
            "attributes": [
                _attribute("id", primary_key=True),
                _attribute("ownerId", column="owner_key"),
                _attribute("title"),
            ],
        },
        {
            "name": "Entry",
            "namespace": "example",
            "table": "entry",
            "inheritance": {"role": "concrete-subtype", "parent": "Ledger"},
            "relationships": [
                {
                    "name": "owner",
                    "cardinality": "many-to-one",
                    "join": {
                        "source": "ownerId",
                        "target": {"entity": "Holder", "attribute": "id"},
                    },
                }
            ],
        },
        {
            "name": "Holder",
            "namespace": "example",
            "table": "holder",
            "attributes": [_attribute("id", primary_key=True)],
        },
    ]


def test_an_inherited_join_endpoint_is_direct_at_the_declaration_that_bears_it() -> None:
    # A join addresses an inherited Attribute at the descendant naming it, while
    # residency is decided over the ancestor's declaration. Role 2 is about the
    # declared Attribute, so `ownerId` keeps its Column and its Override, and the
    # concrete Table carries the Column the join needs.
    definitions = _document_family_joined_through_an_inherited_endpoint()
    validate_storage_layout(definitions)
    layout = compile_storage_layout(definitions).table("entry")
    assert layout is not None
    assert [slot.column for slot in layout.columns] == ["id", "owner_key", "doc"]
    owner = MemberAddress("example.Ledger", ("ownerId",))
    placement = layout.placement(owner)
    assert placement == DirectColumn(layout.column("owner_key"))


def test_tph_participants_are_one_owner_and_tpcs_sibling_columns_may_repeat() -> None:
    validate_storage_layout(_tph_definitions())
    validate_storage_layout(_tpcs_definitions())


def test_unknown_noncanonical_empty_and_cross_family_lookups_are_total() -> None:
    definitions = [*_tpcs_definitions(), _standalone_definition()]
    definitions[-1]["table"] = "standalone"
    facet = compile_storage_layout(definitions)
    assert facet.table("absent") is None
    assert facet.entity("example.Absent") is None
    assert facet.position(()) == facet.position(())
    assert facet.position(("example.Memo", "example.Invoice")) is None
    assert facet.position(("example.Invoice", "example.Invoice")) is None
    assert facet.position(("example.Invoice", "example.Record")) is None
    layout = facet.table("standalone")
    assert layout is not None
    assert layout.column("absent") is None
    assert layout.contribution(AttributeContributor("example.Record", "absent")) is None


def test_private_model_property_caches_the_compiled_layout_graph() -> None:
    model = load_model(_COMPATIBILITY_ROOT, "models/payment.yaml")
    first = model.storage_layout
    second = model.storage_layout
    assert first == second
    assert model.__dict__["storage_layout"] == first


def test_layout_graph_is_immutable_and_structurally_deterministic() -> None:
    model = load_model(_COMPATIBILITY_ROOT, "models/payment.yaml")
    first = compile_storage_layout(model.entity_defs)
    second = compile_storage_layout(model.entity_defs)
    assert first == second
    root = "parallax.compatibility.Payment"
    card = "parallax.compatibility.CardPayment"
    cash = "parallax.compatibility.CashPayment"
    first_position = first.position((card, cash))
    second_position = first.position((card, cash))
    assert first_position == second_position
    layout = first.tables[0]
    with pytest.raises(FrozenInstanceError):
        layout.table = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first.tables = ()  # type: ignore[misc]
    discriminator = layout.contribution(InheritanceDiscriminator(root))
    assert discriminator is not None


@pytest.mark.parametrize("count", [24, 96, 192])
def test_family_fact_compilation_visits_standalone_inputs_linearly(count: int) -> None:
    definitions = _VisitedDefinitions(
        [
            {
                "name": f"Standalone{index}",
                "table": f"standalone_{index}",
                "attributes": [_attribute("id", primary_key=True)],
            }
            for index in range(count)
        ]
    )
    compile_storage_layout(definitions)
    assert definitions.visits == count


def test_large_tph_retained_layout_size_scales_with_schema_not_entity_slot_tuples() -> None:
    small = compile_storage_layout(_large_tph_definitions(24))
    large = compile_storage_layout(_large_tph_definitions(48))
    assert _retained_size(large) < _retained_size(small) * 2.7


def test_entity_columns_are_materialized_on_demand_without_retained_position_growth() -> None:
    facet = compile_storage_layout(_tph_definitions())
    alpha = "example.AlphaRecord"
    beta = "example.BetaRecord"
    before = _retained_size(facet)
    view = facet.entity(alpha)
    assert view is not None
    expected = tuple(view.columns)
    for _ in range(32):
        repeated = facet.entity(alpha)
        assert repeated is not None
        assert tuple(repeated.columns) == expected
        assert facet.position((alpha, beta)) == facet.position((alpha, beta))
    assert _retained_size(facet) == before


def test_ddl_renders_the_complete_shared_table_in_canonical_slot_order() -> None:
    model = _storage_layout_model()
    statement = _create_table_ddl(model, "layout_payment")
    layout = model.storage_layout.table("layout_payment")
    assert layout is not None
    emitted = [
        stripped.split(" ")[0]
        for raw in statement.splitlines()
        if (stripped := raw.strip().rstrip(",")).split(" ")[0]
        not in {"create", "primary", "unique", ")"}
    ]
    assert emitted == [slot.column for slot in layout.columns]
    assert "primary key (id)" in statement


def test_ddl_nullability_is_the_layout_answer_not_authored_nullability() -> None:
    model = _storage_layout_model()
    statement = _create_table_ddl(model, "layout_payment")
    # The model key and the framework-owned discriminator are never nullable, and
    # the family-wide `amount` applies to every row owner of the shared table.
    assert _ddl_column(statement, "id") == "id bigint not null"
    assert _ddl_column(statement, "kind") == "kind varchar(32) not null"
    assert _ddl_column(statement, "amount") == "amount numeric(18,2) not null"
    # Both subtype-only members are REQUIRED of their own concrete Entity yet apply
    # to a strict subset of the shared table's row owners, so the physical columns
    # must accept the sibling variant's rows.
    assert _ddl_column(statement, "card_network") == "card_network varchar(16)"
    assert _ddl_column(statement, "tendered") == "tendered numeric(18,2)"
    # A table-per-concrete-subtype slot applies to its table's only row owner, so it
    # keeps the declared answer even though the same spelling is reused elsewhere.
    assert _ddl_column(_create_table_ddl(model, "layout_audit"), "detail") == (
        "detail varchar(32) not null"
    )
    assert _ddl_column(_create_table_ddl(model, "layout_survey"), "detail") == (
        "detail varchar(32) not null"
    )


def test_ddl_document_slot_follows_every_scalar_tier() -> None:
    statement = _create_table_ddl(_storage_layout_model(), "layout_profile")
    assert _ddl_column(statement, "note") == "note varchar(64)"
    assert _ddl_column(statement, "contact") == "contact jsonb not null"
    assert statement.index("contact jsonb") > statement.index("note varchar(64)")


def test_fixture_load_binds_absent_cells_as_none_in_entity_layout_order() -> None:
    model = _storage_layout_model()
    provider = _RecordingProvider()
    load_fixture_rows(model, cast("Any", provider))
    loads = {
        table: (columns, rows)
        for table, columns, rows in provider.loads
        if table != "layout_payment"
    }

    profile_columns, profile_rows = loads["layout_profile"]
    assert profile_columns == ["id", "label", "note", "contact"]
    # The harness binds every layout column, so an omitted optional cell is an
    # explicit None rather than a skipped column.
    assert profile_rows[1] == [2, "Secondary", None, {"email": "kari@example.test"}]
    assert loads["layout_audit"] == (["id", "title", "detail"], [[1, "Quarterly audit", "Ingrid"]])
    assert loads["layout_survey"] == (["id", "title", "detail"], [[1, "Annual survey", "Bjorn"]])

    # Each shared-table variant loads only the slots applicable to itself, so the
    # sibling's required column is absent from its own column list entirely.
    shared = [entry for entry in provider.loads if entry[0] == "layout_payment"]
    assert [(columns, rows) for _table, columns, rows in shared] == [
        (
            ["id", "kind", "amount", "card_network"],
            [[1, "card", Decimal("100.00"), "Visa"]],
        ),
        (
            ["id", "kind", "amount", "tendered"],
            [[2, "cash", Decimal("20.00"), Decimal("25.00")]],
        ),
    ]


def test_fixture_load_derives_each_variant_discriminator_through_its_view() -> None:
    model = _storage_layout_model()
    provider = _RecordingProvider()
    load_fixture_rows(model, cast("Any", provider))
    variants = [
        (columns[columns.index("kind")], row[columns.index("kind")])
        for table, columns, rows in provider.loads
        if table == "layout_payment"
        for row in rows
    ]
    assert variants == [("kind", "card"), ("kind", "cash")]


def test_a_fixture_row_naming_the_discriminator_is_not_an_authorable_member() -> None:
    model = _storage_layout_model()
    rows = {
        "parallax.compatibility.LayoutCardPayment": [{"id": 9, "amount": "1.00", "kind": "card"}]
    }
    corrupted = Model(model.path, model.descriptor, fixtures=cast("Any", rows))
    with pytest.raises(ValueError, match="unknown member"):
        load_fixture_rows(corrupted, cast("Any", _RecordingProvider()))


def _document_note_model(rows: list[dict[str, Any]]) -> Model:
    """A standalone Relational Document Layout Entity plus its fixture rows.

    Built inline rather than loaded from the corpus so the loader's own answer is
    pinned member by member — a leaf's spelling, an omitted `many`'s empty array,
    and the one shared Structured Column they all land in — against a declaration
    this file states in full.
    """
    definition = _document_standalone(
        attributes=[
            _attribute("id", primary_key=True),
            {"name": "displayName", "type": "string", "nullable": True},
            {"name": "joinedOn", "type": "date", "nullable": True},
        ],
        valueObjects=[
            {
                "name": "address",
                "nullable": True,
                "attributes": [{"name": "city", "type": "string"}],
            },
            {
                "name": "tags",
                "multiplicity": "many",
                "attributes": [{"name": "label", "type": "string"}],
            },
        ],
    )
    return Model(
        Path("models/note.yaml"),
        {"entity": definition},
        fixtures=cast("Any", {"Note": rows}),
    )


def test_fixture_load_composes_one_document_from_a_rows_own_members() -> None:
    model = _document_note_model(
        [
            {
                "id": 1,
                "displayName": "Ada",
                "joinedOn": "2026-01-15",
                "address": {"city": "Oslo"},
                "tags": [{"label": "founder"}],
            }
        ]
    )
    provider = _RecordingProvider()
    load_fixture_rows(model, cast("Any", provider))
    ((table, columns, rows),) = provider.loads
    assert (table, columns) == ("note", ["id", "payload"])
    # Each leaf is authored as the ordinary neutral wire value a direct Column
    # would take and the codec spells it, so one fixture file describes one
    # logical row under either layout.
    assert rows == [
        [
            1,
            {
                "displayName": "Ada",
                "joinedOn": "2026-01-15",
                "address": {"city": "Oslo"},
                "tags": [{"label": "founder"}],
            },
        ]
    ]


def test_fixture_load_keeps_the_document_presence_states_apart() -> None:
    model = _document_note_model([{"id": 2, "displayName": None}])
    provider = _RecordingProvider()
    load_fixture_rows(model, cast("Any", provider))
    ((_table, _columns, rows),) = provider.loads
    # An omitted member contributes no key, an authored null contributes JSON
    # null, and a `many` occurrence always contributes its array.
    assert rows == [[2, {"displayName": None, "tags": []}]]


def test_a_fixture_row_naming_no_document_member_is_still_refused() -> None:
    model = _document_note_model([{"id": 3, "mystery": 1}])
    with pytest.raises(ValueError, match="unknown member"):
        load_fixture_rows(model, cast("Any", _RecordingProvider()))


def _storage_layout_importers() -> list[Path]:
    """The runner, write grading, and every module of the read oracle and the Unit
    Work Scenario package, which import as one boundary.

    Each package is asked as a PACKAGE rather than module by module, so its private
    interior stays free to be rearranged while the set of storage-layout facts the
    harness consumes stays pinned. The universe is every module that grades a case
    against the physical layout, so a fact moving between them is invisible here
    and a change to which names they draw is not.
    """
    return [
        Path(case_preflight.__file__),
        Path(case_runner.__file__),
        Path(statement_bind_inference.__file__),
        Path(write_plan.__file__),
        *_package_modules(object_query_oracle),
        *_package_modules(unit_work_scenario),
    ]


def _package_modules(package: Any) -> list[Path]:
    return sorted(Path(package.__file__).parent.rglob("*.py"))


def _harness_modules() -> list[Path]:
    """Every Python module of the harness — the package and its own suite alike.

    The universe an import rule holds over is every module that could break it, so
    a pin scanning less would pass by omission. This suite is inside it: a test
    reaching past a seam recreates the coupling that seam removes.
    """
    modules = sorted(
        {*Path(case_runner.__file__).parent.rglob("*.py"), *Path(__file__).parent.rglob("*.py")}
    )
    assert Path(__file__) in modules, "the scan missed its own file, so it would hold vacuously"
    return modules


_SOURCE_IMPORT_ROOT = Path(case_runner.__file__).resolve().parents[case_runner.__name__.count(".")]
_TEST_IMPORT_ROOT = Path(__file__).resolve().parents[__name__.count(".")]


def _module_name(path: Path) -> str:
    # Only the directory chain is resolved. Python names a module from the lexical
    # path it was found at beneath sys.path, so following a symlinked module file to
    # its target would anchor its relative imports in the wrong package.
    absolute = path.parent.resolve() / path.name
    for root in (_SOURCE_IMPORT_ROOT, _TEST_IMPORT_ROOT):
        if absolute.is_relative_to(root):
            dotted = ".".join(absolute.relative_to(root).with_suffix("").parts)
            return dotted.removesuffix(".__init__")
    raise AssertionError(f"{path} sits under neither import root, so no name anchors it")


class _ImportEdge(NamedTuple):
    module: str
    member_drawn_from_it: str | None

    @property
    def target(self) -> str:
        member = self.member_drawn_from_it
        return f"{self.module}.{member}" if member else self.module


def _absolute_imports(path: Path) -> Iterator[_ImportEdge]:
    parts = _module_name(path).split(".")
    own_package = parts if path.name == "__init__.py" else parts[:-1]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield _ImportEdge(alias.name, None)
        elif isinstance(node, ast.ImportFrom):
            anchor = own_package[: max(len(own_package) - node.level + 1, 0)] if node.level else []
            base = ".".join([*anchor, *([node.module] if node.module else [])])
            if base:
                yield _ImportEdge(base, None)
            for alias in node.names:
                yield _ImportEdge(base, alias.name) if base else _ImportEdge(alias.name, None)


def test_the_harness_consumes_storage_layout_for_validation_reads_and_observation() -> None:
    facts = f"{storage_layout.__name__}."
    imported = {
        edge.target.removeprefix(facts)
        for path in _storage_layout_importers()
        for edge in _absolute_imports(path)
        if edge.target.startswith(facts)
    }
    assert imported == {
        "AttributeContributor",
        "ColumnContributor",
        "ColumnSlot",
        "ColumnTier",
        "DocumentMember",
        "DocumentPath",
        "MODEL_REJECTED_RULES",
        "MemberAddress",
        "PositionBranch",
        "PositionColumn",
        "PositionLayoutView",
        "RelationalDocument",
        "TableLayout",
        "ValueObjectContributor",
        "member_address",
        "position_projection",
        "position_view",
        "validate_storage_layout",
    }


def test_no_unit_work_scenario_module_imports_case_runner() -> None:
    """The Unit Work Scenario package reaches nothing in the runner.

    The runner imports the package, so an import back is a cycle rather than a
    style question: Scenario grading depends on `write_plan`, `inheritance`, and
    `storage_layout` as authoritative owners rather than on a runner private.
    Asserted over the package as a whole, because which of its modules would do
    the reaching is exactly what may be rearranged.
    """
    modules = _package_modules(unit_work_scenario)
    assert modules, "the package was not found, so this pin would hold vacuously"
    for path in modules:
        for edge in _absolute_imports(path):
            assert "case_runner" not in edge.target, f"{_module_name(path)} imports {edge.target!r}"


def _scenario_suite() -> list[Path]:
    suite = sorted((Path(__file__).parent / "unit_work_scenario").rglob("*.py"))
    assert suite, "the Scenario suite was not found, so a pin over it would hold vacuously"
    return suite


def test_the_scenario_suite_reaches_the_package_only_through_its_one_export() -> None:
    """The package's own suite drives the operation, never a module behind it.

    Compilation, judgement, and grouping are internal seams: a suite module that
    imported one would pin the layout rather than the behaviour, and would
    recreate — one directory over — the private-import surface this package
    exists to remove.
    """
    package = unit_work_scenario.__name__
    for path in _scenario_suite():
        for edge in _absolute_imports(path):
            if edge.module != package and not edge.module.startswith(f"{package}."):
                continue
            member = edge.member_drawn_from_it
            binds_the_package_itself = member is None
            draws_an_export = member in unit_work_scenario.__all__
            assert edge.module == package and (binds_the_package_itself or draws_an_export), (
                f"{_module_name(path)} reaches past the package's exports to {edge.target!r}"
            )


def test_the_oracle_exports_two_names_and_no_retained_type() -> None:
    """The read oracle offers one accepted read and the executor it takes.

    Scenario reads are graded there too, but under no name here: the collaboration
    is package-private, and what a Scenario step retains has no public type,
    constructor, fields, or iteration, so orchestration cannot reach a row, a view,
    or an identity it did not ask a step for.
    """
    assert sorted(object_query_oracle.__all__) == ["ReadExecutor", "assert_case_read"]
    assert not hasattr(object_query_oracle, "ScenarioReads")
    reads = vars(ScenarioReads)
    assert sorted(name for name in reads if not name.startswith("_")) == ["assert_step"]


def test_only_the_scenario_packages_reads_module_imports_the_oracles_scenario_module() -> None:
    """One name, one importer: `ScenarioReads` enters the harness at exactly one module.

    A second importer would make the collaboration an interface again — this time
    an undocumented one — so the rule is pinned over every module of the harness,
    this suite included, rather than stated. Whoever else needs the type asks that
    one module for it, which is what makes the seam a seam.
    """
    reads = Path(unit_work_scenario.__file__).parent / "reads.py"
    importers = {
        path
        for path in _harness_modules()
        for edge in _absolute_imports(path)
        if edge.target.endswith("object_query_oracle.scenario")
    }
    assert importers == {reads}


def test_the_case_runner_holds_no_scenario_helper_of_its_own() -> None:
    """Each Scenario decision has one owner, and the runner is not it.

    The runner reaches the package's own function rather than offering a wrapper
    under the same name, and carries none of these helpers, so a caller asking it
    for one gets an attribute error rather than a second answer to a question the
    package already settles.
    """
    assert case_runner.assert_unit_work_scenario is unit_work_scenario.assert_unit_work_scenario
    for helper in (
        "_assert_scenario",
        "_assert_scenario_count_consistency",
        "_assert_scenario_normalization",
        "_assert_scenario_settled_write",
        "_assert_scenario_source_finds",
        "_assert_scenario_sql_bookkeeping",
        "_assert_scenario_conflict_abort",
        "_is_runner_owned_step",
        "_scenario_uow_groups",
        "_uow_group_is_doomed",
    ):
        assert not hasattr(case_runner, helper), helper


def test_the_harness_retains_no_synthetic_physical_table_entity() -> None:
    # Physical table shape has exactly one owner. A merged Entity standing in for a
    # shared table, or a second Entity-level column sequence, would be a competing
    # answer to the same question the layout already decides.
    assert not hasattr(ddl_builder, "physical_entities_by_table")
    assert not hasattr(ddl_builder, "column_order")
    assert not hasattr(case_runner, "_case_column_order")
