"""m-storage-layout: each Document Table's root-object constraint and its name."""

from __future__ import annotations

import hashlib
from typing import Final

import pytest

from parallax.core.internal import storage_layout
from parallax.core.internal.entity import model_of
from parallax.core.internal.metamodel import Column, EntityIdentity, Metamodel, Table
from parallax.core.internal.storage_layout import (
    DocumentRootConstraint,
    RelationalDocument,
    TableLayout,
    document_root_check_name,
)
from parallax.descriptor import domain_model_from_yaml

_MODEL_YAML: Final = """
entities:
  - name: Note
    namespace: docs
    table: note
    layout: { document: { column: body } }
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: text, type: string }
      - { name: tags, type: string, multiplicity: many }
  - name: Vehicle
    namespace: docs
    table: vehicle
    layout: { document: { column: doc } }
    inheritance: { role: root, strategy: table-per-hierarchy, tag: { column: kind } }
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: label, type: string }
  - name: Car
    namespace: docs
    inheritance: { role: concrete-subtype, parent: docs.Vehicle, tagValue: car }
    attributes:
      - { name: seats, type: int32 }
  - name: Van
    namespace: docs
    inheritance: { role: concrete-subtype, parent: docs.Vehicle, tagValue: van }
    valueObjects:
      - name: cargo
        attributes:
          - { name: volume, type: int32 }
  - name: Ledger
    namespace: docs
    layout: { document: { column: entries } }
    inheritance: { role: root, strategy: table-per-concrete-subtype }
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: title, type: string }
  - name: Invoice
    namespace: docs
    table: invoice
    inheritance: { role: concrete-subtype, parent: docs.Ledger }
    attributes:
      - { name: total, type: int64 }
  - name: Memo
    namespace: docs
    table: memo
    inheritance: { role: concrete-subtype, parent: docs.Ledger }
  - name: Contact
    namespace: docs
    table: contact
    attributes:
      - { name: id, type: int64, primaryKey: true }
      - { name: phones, type: string, multiplicity: many }
    valueObjects:
      - name: address
        nullable: true
        attributes:
          - { name: city, type: string }
"""

_MODEL: Final[Metamodel] = model_of(domain_model_from_yaml(_MODEL_YAML))


def _layout(table: str) -> TableLayout:
    (layout,) = (
        layout
        for layout in storage_layout.storage_layout_facet_of(_MODEL).tables
        if layout.table == Table(table)
    )
    return layout


def _constraint(table: str) -> DocumentRootConstraint:
    layout = _layout(table)
    constraint = layout.document_root_constraint
    assert constraint is not None
    return constraint


@pytest.mark.parametrize(
    ("table", "column"),
    [("note", "body"), ("vehicle", "doc"), ("invoice", "entries"), ("memo", "entries")],
)
def test_each_document_table_constrains_its_own_shared_structured_column(
    table: str, column: str
) -> None:
    layout = _layout(table)
    constraint = _constraint(table)
    assert constraint.slot.column == Column(column)
    assert isinstance(constraint.slot.contributor, RelationalDocument)
    assert layout.contribution(constraint.slot.contributor) is constraint.slot
    assert constraint.slot is layout.columns[-1]


def test_a_shared_table_carries_one_constraint_for_its_whole_family() -> None:
    facet = storage_layout.storage_layout_facet_of(_MODEL)
    car = facet.entity(EntityIdentity("docs", "Car"))
    van = facet.entity(EntityIdentity("docs", "Van"))
    assert car is not None and van is not None
    constraint = _constraint("vehicle")
    assert car.layout.document_root_constraint is constraint
    assert van.layout.document_root_constraint is constraint
    assert constraint.slot.applicable_entities == {car.entity, van.entity}


def test_each_concrete_table_carries_the_constraint_over_its_own_slot() -> None:
    invoice = _constraint("invoice")
    memo = _constraint("memo")
    assert invoice.slot.contributor == memo.slot.contributor
    assert invoice.slot != memo.slot
    assert invoice.slot in _layout("invoice").columns
    assert memo.slot in _layout("memo").columns


def test_a_columns_table_constrains_no_structured_column() -> None:
    layout = _layout("contact")
    assert layout.document_root_constraint is None
    assert {slot.column.name for slot in layout.columns} >= {"phones", "address"}


def _encoded(*fields: str) -> bytes:
    return b"".join(len(field.encode()).to_bytes(4, "big") + field.encode() for field in fields)


def test_the_name_hashes_the_complete_object_operand_encoding() -> None:
    encoding = _encoded("pxc-1", "note", "doc", "1", "object", "1", "body")
    assert document_root_check_name("note", _constraint("note")) == (
        f"pxc_doc_note_{hashlib.sha256(encoding).hexdigest()[:32]}"
    )


def test_the_name_follows_the_physical_table_and_column_and_nothing_else() -> None:
    note = _constraint("note")
    vehicle = _constraint("vehicle")
    assert document_root_check_name("note", note) == document_root_check_name("note", note)
    assert document_root_check_name("vehicle", vehicle) != document_root_check_name("vehicle", note)
    assert document_root_check_name("archive", note) != document_root_check_name("note", note)
    assert document_root_check_name("note", note).startswith("pxc_doc_note_")


@pytest.mark.parametrize(
    "table",
    ["a" * 80, 'Ünïcode Tàble "quoted" name that runs well past the readable budget', "Ωμέγα"],
)
def test_only_the_readable_prefix_bends_to_the_63_byte_budget(table: str) -> None:
    name = document_root_check_name(table, _constraint("note"))
    fingerprint = name.rsplit("_", 1)[1]
    assert len(name.encode("utf-8")) <= 63
    assert name.startswith("pxc_doc_")
    assert len(fingerprint) == 32
    encoding = _encoded("pxc-1", table, "doc", "1", "object", "1", "body")
    assert fingerprint == hashlib.sha256(encoding).hexdigest()[:32]
