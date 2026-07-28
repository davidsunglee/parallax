"""Independent immutable Storage Layout compiler and validation contract."""

from __future__ import annotations

import ast
import dataclasses
import enum
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

import reference_harness.case_runner as case_runner
from reference_harness.case import Model, load_model
from reference_harness.data_loader import load_model as load_fixture_rows
from reference_harness.ddl_builder import ddl_for
from reference_harness.storage_layout import (
    STORAGE_LAYOUT_COLUMN_COLLISION,
    STORAGE_LAYOUT_TABLE_MAPPING_COLLISION,
    AttributeContributor,
    ColumnTier,
    InheritanceDiscriminator,
    ValueObjectContributor,
    _interned,
    _interned_ordinal_selection,
    compile_storage_layout,
    validate_storage_layout,
)
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
    return {
        "name": "Record",
        "namespace": "example",
        "table": "record",
        "attributes": [
            _attribute("id", primary_key=True),
            _attribute("txStart", column="in_z"),
            _attribute("label"),
            _attribute("revisedBy"),
            _attribute("txEnd", column="out_z"),
        ],
        "valueObjects": [{"name": "payload", "column": "payload_doc"}],
        "asOfAxes": [
            {
                "dimension": "transactionTime",
                "startAttribute": "txStart",
                "endAttribute": "txEnd",
            }
        ],
    }


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


def _ranked_temporal_definitions(
    mapping: str, *, duplicate_start: bool
) -> tuple[list[dict[str, Any]], str, str]:
    root = f"example.{mapping.title()}Temporal"
    local_root = root.rpartition(".")[2]
    concrete = f"example.{mapping.title()}TemporalRow"
    shared_start = "validStart" if duplicate_start else "txStart"
    attributes = [
        _attribute("id", primary_key=True),
        _attribute("validStart", column="from_z"),
        _attribute("validEnd", column="thru_z"),
        *([] if duplicate_start else [_attribute("txStart", column="in_z")]),
        _attribute("txEnd", column="out_z"),
    ]
    root_definition: dict[str, Any] = {
        "name": local_root,
        "namespace": "example",
        "attributes": attributes,
        "asOfAxes": [
            {
                "dimension": "transactionTime",
                "startAttribute": shared_start,
                "endAttribute": "txEnd",
            },
            {
                "dimension": "validTime",
                "startAttribute": "validStart",
                "endAttribute": "validEnd",
            },
        ],
    }
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
        AttributeContributor("example.Record", "txStart"),
    ]
    assert [layout.columns.index(slot) for slot in layout.physical_primary_key] == [0, 3]
    payload = layout.contribution(ValueObjectContributor("example.Record", "payload"))
    assert payload is not None
    assert payload.declaring_owner == "example.Record"
    assert payload.applicable_entities == frozenset({"example.Record"})


@pytest.mark.parametrize("mapping", ["standalone", "tph", "tpcs"])
def test_physical_key_temporal_starts_follow_dimension_rank_not_authored_axis_order(
    mapping: str,
) -> None:
    definitions, table, root = _ranked_temporal_definitions(mapping, duplicate_start=False)
    layout = compile_storage_layout(definitions).table(table)
    assert layout is not None
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeContributor(root, "id"),
        AttributeContributor(root, "validStart"),
        AttributeContributor(root, "txStart"),
    ]


@pytest.mark.parametrize("mapping", ["standalone", "tph", "tpcs"])
def test_physical_key_deduplicates_a_start_designated_by_two_dimensions(mapping: str) -> None:
    definitions, table, root = _ranked_temporal_definitions(mapping, duplicate_start=True)
    layout = compile_storage_layout(definitions).table(table)
    assert layout is not None
    assert [slot.contributor for slot in layout.physical_primary_key] == [
        AttributeContributor(root, "id"),
        AttributeContributor(root, "validStart"),
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
        (["id", "kind", "amount", "card_network"], [[1, "card", 100.00, "Visa"]]),
        (["id", "kind", "amount", "tendered"], [[2, "cash", 20.00, 25.00]]),
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
    rows = {"parallax.compatibility.LayoutCardPayment": [{"id": 9, "amount": 1.00, "kind": "card"}]}
    corrupted = Model(model.path, model.descriptor, fixtures=cast("Any", rows))
    with pytest.raises(ValueError, match="unknown member"):
        load_fixture_rows(corrupted, cast("Any", _RecordingProvider()))


def test_case_runner_consumes_storage_layout_for_validation_and_read_projection() -> None:
    source = Path(case_runner.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "storage_layout"
        for alias in node.names
    }
    assert imported == {
        "ColumnSlot",
        "PositionBranch",
        "PositionColumn",
        "PositionLayoutView",
        "STORAGE_LAYOUT_MODEL_REJECTED_RULES",
        "position_projection",
        "position_view",
        "validate_storage_layout",
    }
