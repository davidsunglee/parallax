"""Inheritance-family read lowering (m-sql "Metamodel-extension lowering").

The corpus inheritance cases are the byte-exact acceptance surface for the tag
predicate, its bind order and grouping, and each strategy's projection order
(`test_compile_sweep` / `test_run_sweep`); these unit tests pin what the corpus
does not isolate: synthetic families, the statement shapes a document-variant
partition takes, the per-branch alias and bind state a table-per-concrete-subtype
`union all` restarts, delivery of family rows, and the read's result contract.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Literal

import pytest

from parallax.core import UnsupportedError
from parallax.core.internal import continuation, inheritance, read_planning, storage_layout
from parallax.core.internal import object_query as oq
from parallax.core.internal import predicate as oa
from parallax.core.internal.base import StructuredDocument, UsageError
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.entity._model import model_of
from parallax.core.internal.metamodel import AttributeMetadata, EntityIdentity, Metamodel
from parallax.core.internal.object_query._nodes import TemporalDimension
from parallax.core.internal.read_delivery._page import MISSING_STORED_VALUE
from parallax.core.internal.read_planning import ResolvedReadProjection
from parallax.core.internal.sql_gen import _compile as sql_compile
from parallax.core.internal.sql_gen._inheritance import (
    INHERITANCE_LOCKING_READ_UNSUPPORTED,
    ReadResultContract,
    plan_document_reads,
)
from parallax.core.internal.sql_gen._predicate import render_predicate
from tests._support.bindings import bound_model
from tests._support.errors import raises_code
from tests._support.sql import compile_nonempty_read, compile_projected_read, compile_read
from tests.unit import _family_predecessor_support as family
from tests.unit import _read_projection_support as support
from tests.unit._corpus_model_support import formed, model, target
from tests.unit.core.sql_gen._delivery_support import deliver
from tests.unit.core.sql_gen._plan_reuse_support import record_plan_reuse

PAYMENT = model("payment")
ANIMAL = model("animal")
APPLIANCE = model("appliance")
DOCUMENT = model("document")
DOCUMENT_LAYOUT = model("document-layout")
MATERIALIZATION_KEYS = model("materialization-key-compatibility")
COMPOSED_BEAST = model("composed-beast-reader")
COMPOSED_DOCUMENT_BEAST = model("composed-beast-document-reader")


def _narrow(model_: Any, *names: str) -> tuple[Any, ...]:
    return tuple(target(model_, name).identity for name in names)


def test_document_fan_out_references_complete_residency_while_selecting_only_attributes() -> None:
    entity = target(DOCUMENT_LAYOUT, "Voyage")
    storage = storage_layout.storage_layout_facet_of(DOCUMENT_LAYOUT)
    physical = storage.entity(entity.identity)
    position = storage.position((entity.identity,))
    assert physical is not None and position is not None
    residents = physical.document_residents
    assert residents is not None
    bindings = [residents.member_selection.bindings[position] for position in residents.positions]
    assert any(not isinstance(binding, AttributeMetadata) for binding in bindings)

    shared, _direct = plan_document_reads(
        position,
        inheritance.inheritance_facet_of(DOCUMENT_LAYOUT),
        storage,
        ResolvedReadProjection((), False),
    )

    assert shared is not None
    ((identity, fan_out),) = shared.per_entity
    assert identity == entity.identity
    assert fan_out.shape is residents.shape
    assert fan_out.members == tuple(
        (binding.storage.name, placement.path)
        for binding, placement in zip(bindings, residents.placements, strict=True)
        if isinstance(binding, AttributeMetadata)
    )
    assert len(residents.shape.members) > len(fan_out.members)


def test_narrow_nested_under_a_table_per_concrete_subtype_family_partitions_branches() -> None:
    # A TPCS union evaluates a nested narrow against each concrete branch: the
    # selected branches receive true and every other branch receives false.
    op = oa.Or(
        operands=(
            oa.Narrow(to=("Invoice",), operand=oa.TrueNode()),
            oa.Narrow(to=("Memo",), operand=oa.TrueNode()),
        )
    )
    compiled = compile_read(op, bound_model(DOCUMENT), POSTGRES, target(DOCUMENT, "Document"))
    assert compiled.statement.sql.endswith(
        "from px.invoice t0 where 1 = 1 or 1 = 0 union all "
        "select t0.id, t0.title, t0.folder_id, cast(null as varchar(3)) currency, "
        "cast(null as decimal(18, 2)) amount_due, t0.body, "
        "cast(null as decimal(18, 2)) paid_amount, 'Memo' family_variant "
        "from px.memo t0 where 1 = 0 or 1 = 1 union all "
        "select t0.id, t0.title, t0.folder_id, t0.currency, "
        "cast(null as decimal(18, 2)) amount_due, cast(null as varchar(64)) body, "
        "t0.paid_amount, 'Receipt' family_variant from px.receipt t0 where 1 = 0 or 1 = 0"
    )
    assert compiled.statement.binds == ()


def test_a_disjunctive_narrow_operand_stays_whole_inside_its_tpcs_branch() -> None:
    op = oa.And(
        operands=(
            oa.Narrow(
                to=("Invoice",),
                operand=oa.Or(
                    operands=(
                        oa.Comparison(op="eq", subject=oa.FieldSubject("Invoice.title"), value="a"),
                        oa.Comparison(op="eq", subject=oa.FieldSubject("Invoice.title"), value="b"),
                    )
                ),
            ),
            oa.Comparison(op="eq", subject=oa.FieldSubject("Document.folderId"), value=7),
        )
    )
    compiled = compile_read(op, bound_model(DOCUMENT), POSTGRES, target(DOCUMENT, "Document"))
    assert "from px.invoice t0 where (t0.title = ? or t0.title = ?) and t0.folder_id = ?" in (
        compiled.statement.sql
    )


TRAVERSAL = model("predicate-traversal")


def _volvo_with_more_than(seats: int) -> oa.And:
    return oa.And(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Vehicle.maker"), value="Volvo"),
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Car.seats"), value=seats),
        )
    )


@pytest.mark.parametrize(
    "narrowed",
    [
        oa.Narrow(to=("Car",), operand=_volvo_with_more_than(5)),
        oa.Narrow(to=("Car",), operand=oa.Narrow(to=("Car",), operand=_volvo_with_more_than(5))),
    ],
)
def test_a_negated_conjunctive_narrow_is_negated_whole_inside_its_tpcs_branch(
    narrowed: oa.Narrow,
) -> None:
    compiled = compile_read(
        oa.Not(narrowed),
        bound_model(TRAVERSAL),
        POSTGRES,
        target(TRAVERSAL, "Vehicle"),
    )
    assert "from px.traversal_bike t0 where not 1 = 0 union all " in compiled.statement.sql
    assert compiled.statement.sql.endswith(
        "from px.traversal_car t0 where not (t0.maker = ? and t0.seats > ?)"
    )


def test_a_negated_conjunctive_narrow_is_negated_whole_inside_a_quantifier() -> None:
    op = oa.Quantifier(
        "any",
        "Folder.documents",
        oa.Not(
            oa.Narrow(
                to=("Invoice",),
                operand=oa.And(
                    operands=(
                        oa.Comparison(op="eq", subject=oa.FieldSubject("title"), value="a"),
                        oa.Comparison(op="eq", subject=oa.FieldSubject("currency"), value="EUR"),
                    )
                ),
            )
        ),
    )
    compiled = compile_read(op, bound_model(DOCUMENT), POSTGRES, target(DOCUMENT, "Folder"))
    assert "t1.folder_id = t0.id and not (t1.title = ? and t1.currency = ?))" in (
        compiled.statement.sql
    )


def test_tpcs_document_single_branch_projects_its_document() -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Publication"),
        narrow_to=_narrow(DOCUMENT_LAYOUT, "Book"),
        result_form="instance",
    )
    assert compiled.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload from px.publication_book t0"
    )


def test_tph_disjunctive_branch_predicate_stays_whole_beside_its_tag() -> None:
    either = oa.Or(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Animal.name"), value="Whiskers"),
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Dog.barkVolume"), value=5),
        )
    )
    narrowed = compile_read(
        oa.Narrow(to=("Dog",), operand=either),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert narrowed.statement.sql.endswith(
        "where ((t0.name = ? or t0.bark_volume > ?) and t0.kind = ?)"
    )
    concrete = compile_read(
        oa.Or(
            operands=(
                oa.Comparison(op="eq", subject=oa.FieldSubject("Dog.name"), value="Whiskers"),
                oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Dog.barkVolume"), value=5),
            )
        ),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Dog"),
    )
    assert concrete.statement.sql.endswith(
        "where (t0.name = ? or t0.bark_volume > ?) and t0.kind = ?"
    )


def test_tph_top_level_narrow_partitions_before_variant_specific_document_cast() -> None:
    compiled = compile_read(
        oa.Comparison(
            op="greaterThan", subject=oa.FieldSubject("CashPayment.detail"), value="10.00"
        ),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
        narrow_to=_narrow(DOCUMENT_LAYOUT, "CashPayment"),
    )

    assert (
        "from (select * from px.payment_document t0 where t0.kind = ? offset 0) p1"
        in compiled.statement.sql
    )
    assert compiled.statement.sql.endswith(
        "where cast(jsonb_extract_path_text(p1.payload, ?) as decimal(18, 2)) > ?"
    )
    assert compiled.statement.binds == ("cash", "detail", Decimal("10.0"))


def _heterogeneous_payment_predicate() -> oa.PredicateNode:
    return oa.Or(
        operands=(
            oa.Narrow(
                to=("CardPayment",),
                operand=oa.Comparison(
                    op="eq", subject=oa.FieldSubject("CardPayment.detail"), value="visa-4242"
                ),
            ),
            oa.Narrow(
                to=("CashPayment",),
                operand=oa.Comparison(
                    op="greaterThan", subject=oa.FieldSubject("CashPayment.detail"), value="10.00"
                ),
            ),
        )
    )


@pytest.fixture
def rendered_roots(monkeypatch: pytest.MonkeyPatch) -> list[tuple[bool, tuple[Any, ...], int]]:
    """For each lexical root a compiled read renders: whether its plan
    partitions, that plan's root keys, and the root rendered."""
    roots: list[tuple[bool, tuple[Any, ...], int]] = []
    real = render_predicate

    def render(**kwargs: Any) -> str:
        plan = kwargs["statement_plan"]
        roots.append((plan.requires_tph_partition, tuple(plan.root_scopes), kwargs["scope_id"]))
        return real(**kwargs)

    monkeypatch.setattr(sql_compile, "_render_predicate", render)
    return roots


def test_a_partitioning_tph_read_renders_only_its_planned_partitions(
    rendered_roots: list[tuple[bool, tuple[Any, ...], int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reuse = record_plan_reuse(monkeypatch)
    compiled = compile_read(
        _heterogeneous_payment_predicate(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
    )
    concretes = _narrow(DOCUMENT_LAYOUT, "CardPayment", "CashPayment")
    assert compiled.read_shape.variant == "tph-partitioned"
    assert tuple(root.concrete for root in compiled.read_shape.roots) == concretes
    assert {root.mapping_owner for root in compiled.read_shape.roots} == set(
        _narrow(DOCUMENT_LAYOUT, "Payment")
    )
    assert not compiled.read_shape.is_union
    assert not compiled.result_contract.may_repeat_row_keys
    assert [(partitions, keys) for partitions, keys, _root in rendered_roots] == [
        (True, concretes)
    ] * 2
    assert len({root for _partitions, _keys, root in rendered_roots}) == 2
    (plan,) = reuse.plans
    assert [(root.statement_plan, root.scope_id) for root in reuse.roots] == [
        (plan, plan.root_scopes[concrete]) for concrete in concretes
    ]
    assert len({id(root.row.ctx) for root in reuse.roots}) == 2


@pytest.mark.parametrize(
    ("order_by", "partitions"),
    [
        ((oq.OrderKey(attr="CashPayment.detail", direction="asc"),), True),
        ((oq.OrderKey(attr="Payment.id", direction="asc"),), False),
    ],
    ids=["document-member", "direct-member"],
)
def test_a_tph_ordering_term_alone_decides_partitioning_before_rendering(
    rendered_roots: list[tuple[bool, tuple[Any, ...], int]],
    order_by: tuple[oq.OrderKey, ...],
    partitions: bool,
) -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
        narrow_to=_narrow(DOCUMENT_LAYOUT, "CashPayment"),
        order_by=order_by,
    )
    (partitioned, keys, _root), *_ = rendered_roots
    assert partitioned is partitions
    assert keys == (_narrow(DOCUMENT_LAYOUT, "CashPayment") if partitions else (None,))
    assert len(rendered_roots) == 1
    assert ("offset 0) p1" in compiled.statement.sql) is partitions
    assert compiled.read_shape.variant == ("tph-partitioned" if partitions else "single-table")


def _ticket_family() -> Metamodel:
    """A table-per-hierarchy ``Document``-layout family whose concretes declare
    one Document Path at incompatible types, so a predicate on it partitions by
    variant: a resident scalar collection on the root, and a resident Value
    Object only ``CardTicket`` declares."""
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Inheritance,
        ValueObject,
        ValueObjectAttribute,
    )
    from parallax.descriptor._records import Metamodel as Records

    return formed(
        Records(
            entities=(
                Entity(
                    name="Ticket",
                    table="ticket",
                    layout=DocumentLayout(column="payload"),
                    inheritance=Inheritance(
                        role="root", strategy="table-per-hierarchy", tag_column="kind"
                    ),
                    attributes=(
                        Attribute(name="id", type="int64", column="id", primary_key=True),
                        Attribute(
                            name="labels", type="string", column="labels", multiplicity="many"
                        ),
                    ),
                ),
                Entity(
                    name="CardTicket",
                    inheritance=Inheritance(
                        role="concrete-subtype", parent="Ticket", tag_value="card"
                    ),
                    attributes=(Attribute(name="detail", type="string", column="detail"),),
                    value_objects=(
                        ValueObject(
                            name="stamp",
                            nullable=True,
                            attributes=(ValueObjectAttribute(name="mark", type="string"),),
                        ),
                    ),
                ),
                Entity(
                    name="CashTicket",
                    inheritance=Inheritance(
                        role="concrete-subtype", parent="Ticket", tag_value="cash"
                    ),
                    attributes=(Attribute(name="detail", type="numeric(18,2)", column="detail"),),
                ),
            )
        )
    )


TICKETS = _ticket_family()
_TICKET_PREDICATE = oa.Or(
    operands=(
        oa.Narrow(
            to=("CardTicket",),
            operand=oa.Comparison(
                op="eq", subject=oa.FieldSubject("CardTicket.detail"), value="visa"
            ),
        ),
        oa.Narrow(
            to=("CashTicket",),
            operand=oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Ticket.id"), value=0),
        ),
    )
)
_CARD_BRANCH = (
    "(select * from px.ticket {table} where {table}.kind = ? offset 0) p1 "
    "where jsonb_extract_path_text(p1.payload, ?) = ? or 1 = 0"
)
_CASH_BRANCH = (
    "(select * from px.ticket {table} where {table}.kind = ? offset 0) p2 where 1 = 0 or p2.id > ?"
)
_TICKET_SQL = {
    "bare": (
        "select p1.id, p1.kind, not p1.payload is null, p1.payload from "
        + _CARD_BRANCH.format(table="t0")
        + " union all select p2.id, p2.kind, not p2.payload is null, p2.payload from "
        + _CASH_BRANCH.format(table="t0")
    ),
    "wrapped": (
        "select u.id, u.kind, not u.payload is null, u.payload from ("
        "select p1.id, p1.kind, p1.payload from "
        + _CARD_BRANCH.format(table="t0")
        + " union all select p2.id, p2.kind, p2.payload from "
        + _CASH_BRANCH.format(table="t0")
        + ") u order by u.id asc limit ?"
    ),
    "locking": (
        "select t0.id, t0.kind, not t0.payload is null, t0.payload from px.ticket t0 join ("
        "select p1.id from "
        + _CARD_BRANCH.format(table="t1")
        + " union all select p2.id from "
        + _CASH_BRANCH.format(table="t2")
        + ") u on u.id = t0.id limit ? for share of t0"
    ),
}
# Stored rows: a full card, a card whose collection and occurrence hold JSON
# null, a cash row lacking every optional key, and cash rows whose required
# `detail` is JSON null, a missing key, or missing because the whole Structured
# Column is SQL NULL.
_TICKET_ROWS: tuple[dict[str, object], ...] = (
    {
        "id": 1,
        "kind": "card",
        "payload": {"detail": "visa", "labels": ["a"], "stamp": {"mark": "m"}},
    },
    {"id": 2, "kind": "card", "payload": {"detail": "visa", "labels": None, "stamp": None}},
    {"id": 3, "kind": "cash", "payload": {"detail": "12.50"}},
    {"id": 4, "kind": "cash", "payload": {"detail": None, "labels": ["b", "c"]}},
    {"id": 5, "kind": "cash", "payload": {"labels": []}},
    {"id": 6, "kind": "cash", "payload": None},
)


def _ticket_delivery(form: Literal["row", "instance"]) -> list[tuple[object, ...]]:
    stamped = form == "instance"
    card_document = {"detail": "visa", "labels": ["a"], "stamp": {"mark": "m"}}
    null_document = {"detail": "visa", "labels": None, "stamp": None}
    return [
        (
            "CardTicket",
            {
                "id": 1,
                "labels": ("a",),
                "detail": "visa",
                **({"stamp": {"mark": "m"}} if stamped else {}),
            },
            (),
            card_document,
        ),
        (
            "CardTicket",
            {"id": 2, "labels": (), "detail": "visa", **({"stamp": None} if stamped else {})},
            (),
            null_document,
        ),
        (
            "CashTicket",
            {"id": 3, "labels": (), "detail": Decimal("12.50")},
            (),
            {"detail": "12.50"},
        ),
        (
            "CashTicket",
            {"id": 4, "labels": ("b", "c")},
            (("stored-data-attribute-null", None),),
            {"detail": None, "labels": ["b", "c"]},
        ),
        (
            "CashTicket",
            {"id": 5, "labels": ()},
            (("stored-data-attribute-null", MISSING_STORED_VALUE),),
            {"labels": []},
        ),
        (
            "CashTicket",
            {"id": 6, "labels": ()},
            (("stored-data-attribute-null", MISSING_STORED_VALUE),),
            None,
        ),
    ]


@pytest.mark.parametrize("form", ["row", "instance"])
@pytest.mark.parametrize("shape", ["bare", "wrapped", "locking"])
def test_every_partitioned_tph_statement_delivers_the_same_rows(
    shape: Literal["bare", "wrapped", "locking"], form: Literal["row", "instance"]
) -> None:
    # The three statement shapes a variant-partitioned read takes carry one
    # result: each outermost select list is folded, converted, and judged
    # identically, whether the document pair is selected from a branch, through
    # the derived union, or off the locked base row.
    options: dict[str, Any] = {
        "bare": {},
        "wrapped": {"order_by": (oq.OrderKey(attr="Ticket.id", direction="asc"),), "limit": 5},
        "locking": {"limit": 5, "preference": "locking"},
    }[shape]
    compiled = compile_read(
        _TICKET_PREDICATE,
        bound_model(TICKETS),
        POSTGRES,
        target(TICKETS, "Ticket"),
        result_form=form,
        **options,
    )

    assert compiled.statement.sql == _TICKET_SQL[shape]
    assert compiled.statement.binds == (
        "card",
        "detail",
        "visa",
        "cash",
        0,
        *((5,) if shape != "bare" else ()),
    )
    assert compiled.document_reads == ((2, 3),)
    delivered = deliver(TICKETS, compiled, _TICKET_ROWS)
    assert [(row.entity, row.members, row.issues, row.document) for row in delivered] == (
        _ticket_delivery(form)
    )


def test_tph_document_classification_uses_only_the_tagged_variant_shape() -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Payment"),
        result_form="instance",
    )

    card, cash, wire = deliver(
        DOCUMENT_LAYOUT,
        compiled,
        [
            {
                "id": 1,
                "kind": "card",
                "payload": {"detail": "visa-4242", "authorizationCode": "AUTH-7"},
            },
            {"id": 2, "kind": "cash", "payload": {"detail": "12.50"}},
            {"id": 3, "kind": "wire", "payload": {"detail": "x"}},
        ],
    )
    assert (card.entity, card.issues) == ("CardPayment", ())
    assert card.members == {"id": 1, "detail": "visa-4242", "authorizationCode": "AUTH-7"}
    assert (cash.entity, cash.issues) == ("CashPayment", ())
    assert cash.members == {"id": 2, "detail": Decimal("12.50")}
    assert wire.entity == "Payment"
    assert wire.issues == (("stored-data-family-tag-unknown", "wire"),)


def test_tph_concrete_document_read_uses_only_that_variants_shape() -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "CardPayment"),
    )

    (card,) = deliver(
        DOCUMENT_LAYOUT,
        compiled,
        [{"id": 1, "payload": {"detail": "visa-4242", "authorizationCode": "AUTH-7"}}],
    )
    assert (card.entity, card.issues) == ("CardPayment", ())
    assert card.members == {"id": 1, "detail": "visa-4242", "authorizationCode": "AUTH-7"}


def test_tph_concrete_target_names_its_rows_without_reading_a_carrier() -> None:
    # A concrete target projects no discriminator (m-inheritance-012's switch is
    # the queried target's role), so its identity is fixed when the read is
    # compiled: every row names that concrete, read off no tag column, and
    # `resolvable` is the concrete alone rather than the
    # family the tag map would reach.
    compiled = compile_read(
        oa.TrueNode(), bound_model(PAYMENT), POSTGRES, target(PAYMENT, "CardPayment")
    )
    card = target(PAYMENT, "CardPayment").identity
    assert compiled.statement.sql.startswith("select t0.id, t0.amount, t0.card_network from")
    assert compiled.result_contract.identity_ordinal is None
    (row,) = deliver(PAYMENT, compiled, [{"id": 1, "amount": 10, "card_network": "visa"}])
    assert (row.entity, row.issues) == ("CardPayment", ())
    assert compiled.result_contract.resolvable == (card,)


def test_tph_document_family_with_no_resident_members_projects_no_document() -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Inheritance,
        Metamodel,
    )

    root = Entity(
        name="EmptyRoot",
        table="empty_root",
        layout=DocumentLayout(column="payload"),
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    concrete = Entity(
        name="EmptyLeaf",
        inheritance=Inheritance(role="concrete-subtype", parent="EmptyRoot", tag_value="leaf"),
    )
    meta = formed(Metamodel(entities=(root, concrete)))

    compiled = compile_read(oa.TrueNode(), bound_model(meta), POSTGRES, target(meta, "EmptyRoot"))
    assert compiled.statement.sql == "select t0.id, t0.kind from px.empty_root t0"
    (row,) = deliver(meta, compiled, [{"id": 1, "kind": "leaf"}])
    assert (row.entity, row.issues) == ("EmptyLeaf", ())


@pytest.mark.parametrize(
    ("strategy", "shared_table"),
    [("table-per-hierarchy", "mixed_family"), ("table-per-concrete-subtype", None)],
)
def test_a_family_document_keeps_an_unselected_occurrence_only_resident_shape(
    strategy: Literal["table-per-hierarchy", "table-per-concrete-subtype"],
    shared_table: str | None,
) -> None:
    from parallax.descriptor._records import (
        Attribute,
        DocumentLayout,
        Entity,
        Inheritance,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    root = Entity(
        name="MixedRoot",
        table=shared_table,
        layout=DocumentLayout(column="payload"),
        inheritance=Inheritance(
            role="root",
            strategy=strategy,
            tag_column="kind" if shared_table is not None else None,
        ),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    scalar = Entity(
        name="ScalarLeaf",
        table=None if shared_table is not None else "scalar_leaf",
        inheritance=Inheritance(
            role="concrete-subtype",
            parent="MixedRoot",
            tag_value="scalar" if shared_table is not None else None,
        ),
        attributes=(Attribute(name="detail", type="string", column="detail"),),
    )
    occurrence = Entity(
        name="OccurrenceLeaf",
        table=None if shared_table is not None else "occurrence_leaf",
        inheritance=Inheritance(
            role="concrete-subtype",
            parent="MixedRoot",
            tag_value="occurrence" if shared_table is not None else None,
        ),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    meta = formed(Metamodel(entities=(root, scalar, occurrence)))

    compiled = compile_read(oa.TrueNode(), bound_model(meta), POSTGRES, target(meta, "MixedRoot"))

    assert "payload" in compiled.statement.sql


def test_tph_equivalent_narrow_spellings_collapse() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its explicit concrete
    # descendants) resolve to the same effective set and MUST lower identically,
    # regardless of the authored `to` order or spelling (m-predicate / m-sql).
    by_abstract = compile_read(
        oa.Narrow(to=("Pet",), operand=oa.TrueNode()),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    by_concretes = compile_read(
        oa.Narrow(to=("Dog", "Cat"), operand=oa.TrueNode()),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    # The LOWERING is what must collapse. `narrow_to` deliberately does not: it
    # reports the narrow the caller AUTHORED, which materialization resolves for
    # itself — so the two compiled reads are compared statement to statement.
    assert by_abstract.statement == by_concretes.statement


def test_tph_narrow_canonical_alphabetical_order_independent_of_authored_order() -> None:
    # The `to` list's authored order never leaks into the lowered `in (...)` list —
    # it is always the family's canonical alphabetical order.
    compiled = compile_read(
        oa.Narrow(to=("Dog", "Cat"), operand=oa.TrueNode()),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.endswith("where t0.kind in (?, ?)")
    assert compiled.statement.binds == ("cat", "dog")


def test_tpcs_union_restarts_aliases_per_branch_and_concatenates_binds() -> None:
    # The state invariant behind the union lane: each `union all` branch gets its
    # OWN lowering context, so a branch's shared join restarts at `t1` rather than
    # continuing the previous branch's sequence, and the branch bind lists
    # concatenate in the branches' canonical alphabetical order.
    from parallax.descriptor._records import (
        Attribute,
        DefiningRelationship,
        Entity,
        Inheritance,
        Metamodel,
        RelationshipJoin,
        RelationshipTarget,
    )

    root = Entity(
        name="Doc",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="title", type="string", column="title", max_length=32),
            Attribute(name="ownerId", type="int64", column="owner_id", nullable=True),
        ),
        relationships=(
            DefiningRelationship(
                name="owner",
                cardinality="many-to-one",
                join=RelationshipJoin(
                    source="ownerId", target=RelationshipTarget(entity="Owner", attribute="id")
                ),
            ),
        ),
    )
    invoice = Entity(
        name="Inv",
        table="inv",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="due", type="int32", column="due"),),
    )
    receipt = Entity(
        name="Rec",
        table="rec",
        inheritance=Inheritance(role="concrete-subtype", parent="Doc"),
        attributes=(Attribute(name="paid", type="int32", column="paid"),),
    )
    owner = Entity(
        name="Owner",
        table="owner",
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="name", type="string", column="name", max_length=32),
        ),
    )
    meta = formed(Metamodel(entities=(root, invoice, receipt, owner)))

    op = oa.And(
        operands=(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Doc.title"), value="T"),
            oa.Comparison(op="eq", subject=oa.FieldSubject("Doc.owner.name"), value="N"),
            oa.Presence(
                "exists",
                "Doc.owner",
                oa.Comparison(op="eq", subject=oa.FieldSubject("name"), value="M"),
            ),
        )
    )
    compiled = compile_read(op, bound_model(meta), POSTGRES, target(meta, "Doc"))
    branches = compiled.statement.sql.split(" union all ")
    assert len(branches) == 2
    # BOTH branches restart the whole sequence: base `t0`, join alias `t1`, and a
    # match reusing that join with no alias of its own.
    joined = (
        "left join px.owner t1 on t1.id = t0.owner_id where t0.title = ? and t1.name = ? "
        "and case when t1.id is null then false else (t1.name = ?) is true end"
    )
    assert branches[0] == (
        "select t0.id, t0.title, t0.owner_id, t0.due, cast(null as int) paid, "
        f"'Inv' family_variant from px.inv t0 {joined}"
    )
    assert branches[1] == (
        "select t0.id, t0.title, t0.owner_id, cast(null as int) due, t0.paid, "
        f"'Rec' family_variant from px.rec t0 {joined}"
    )
    # Per-branch binds, concatenated in alphabetical branch order — never merged,
    # deduplicated, or reordered.
    assert compiled.statement.binds == ("T", "N", "M", "T", "N", "M")


def test_tpcs_equivalent_narrow_spellings_collapse() -> None:
    by_abstract = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "Document"),
        narrow_to=_narrow(DOCUMENT, "FinancialDocument"),
    )
    by_concretes = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "Document"),
        narrow_to=_narrow(DOCUMENT, "Receipt", "Invoice"),
    )
    assert by_abstract.statement == by_concretes.statement
    # And matches reading the abstract subtype directly, no narrow at all.
    direct = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "FinancialDocument"),
    )
    assert by_abstract.statement == direct.statement


def test_tph_nested_narrow_with_a_trivial_branch_needs_no_grouping() -> None:
    # A nested narrow whose own operand is `all` (no extra predicate) lowers to the
    # bare tag fragment alone — a single term needs no disambiguating parens, unlike
    # its sibling branch here, which does compose a predicate with its tag guard.
    compiled = compile_read(
        oa.Or(
            operands=(
                oa.Narrow(to=("Dog",), operand=oa.TrueNode()),
                oa.Narrow(
                    to=("Cat",),
                    operand=oa.Comparison(
                        op="eq", subject=oa.FieldSubject("Cat.indoor"), value=True
                    ),
                ),
            )
        ),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    assert compiled.statement.sql.endswith("where t0.kind = ? or (t0.indoor = ? and t0.kind = ?)")
    assert compiled.statement.binds == ("dog", True, "cat")


def test_tph_abstract_instance_form_projects_the_value_object_document_last() -> None:
    # A synthetic table-per-hierarchy family proves the layout tier order for a
    # value object: the `Identity` slot, the raw `Discriminator`
    # slot, the `Domain` slot, THEN the `Document` slot, which rides last among
    # ALL columns however early its owner declares it (m-sql *Read projection*).
    from parallax.descriptor._records import (
        Attribute,
        Entity,
        Inheritance,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    meta = formed(Metamodel(entities=(root, leaf)))
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(meta),
        POSTGRES,
        target(meta, "Root"),
        result_form="instance",
    )
    assert compiled.statement.sql == (
        "select t0.id, t0.kind, t0.x, not t0.meta is null, t0.meta from px.root_tbl t0"
    )
    tagged, unknown = deliver(
        meta,
        compiled,
        [
            {"id": 1, "kind": "leaf", "x": 7, "meta": {"note": "tagged"}},
            {"id": 2, "kind": "unknown", "x": None, "meta": {"note": "unclassified"}},
        ],
    )
    assert (tagged.entity, tagged.issues) == ("Leaf", ())
    assert tagged.members == {"id": 1, "x": 7, "meta": {"note": "tagged"}}
    assert unknown.entity == "Root"
    assert unknown.members == {"id": 2, "meta": {"note": "unclassified"}}
    assert unknown.issues == (("stored-data-family-tag-unknown", "unknown"),)


def test_tpcs_literal_identity_selects_the_direct_value_object_contract() -> None:
    # A union branch resolves its concrete through the synthetic literal before
    # the direct document wrapper chooses that concrete's occurrence contract.
    from parallax.descriptor._records import (
        Attribute,
        Entity,
        Inheritance,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    root = Entity(
        name="Root",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(
            Attribute(name="id", type="int64", column="id", primary_key=True),
            Attribute(name="payload", type="bytes", column="payload", nullable=True),
        ),
        value_objects=(
            ValueObject(
                name="meta",
                column="meta",
                attributes=(ValueObjectAttribute(name="note", type="string"),),
            ),
        ),
    )
    first = Entity(
        name="First",
        table="first_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
    )
    second = Entity(
        name="Second",
        table="second_tbl",
        inheritance=Inheritance(role="concrete-subtype", parent="Root"),
    )
    meta = formed(Metamodel(entities=(root, first, second)))
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(meta),
        POSTGRES,
        target(meta, "Root"),
        result_form="instance",
    )
    (row,) = deliver(
        meta,
        compiled,
        [{"id": 1, "payload": "00ff", "meta": {"note": "literal"}, "family_variant": "First"}],
    )
    assert (row.entity, row.issues) == ("First", ())
    assert row.members == {"id": 1, "payload": b"\x00\xff", "meta": {"note": "literal"}}


def test_tph_tag_identity_holds_regardless_of_narrow_cardinality() -> None:
    # m-inheritance-012's own witness: narrowed down to ONE concrete, but the read's
    # OWN queried `target` (Animal) is abstract, so the tag column is still projected
    # and still transformed. The map is the WHOLE family's, not the narrow's
    # resolved position — `WildBoar` is outside the narrow and still maps.
    compiled = compile_read(
        oa.Narrow(to=("Dog",), operand=oa.TrueNode()),
        bound_model(ANIMAL),
        POSTGRES,
        target(ANIMAL, "Animal"),
    )
    dog, boar = deliver(ANIMAL, compiled, [{"id": 1, "kind": "dog"}, {"id": 2, "kind": "boar"}])
    assert (dog.entity, dog.issues) == ("Dog", ())
    # The sibling the narrow excluded is named ahead of any row: `resolvable`
    # is the whole tag map plus the family root, so a consumer preparing one
    # structure per Entity a row can carry prepares WildBoar's before the boar
    # row arrives rather than on reaching it.
    assert (boar.entity, boar.issues) == ("WildBoar", ())
    assert set(compiled.result_contract.resolvable) == {
        target(ANIMAL, name).identity for name in ("Animal", "Cat", "Dog", "WildBoar")
    }


def test_a_narrow_to_every_composed_concrete_keeps_its_tag_guard() -> None:
    # A composed set equal to the family's never stands in for the unnarrowed
    # root, whose read alone spans the whole shared table (m-sql).
    broad = compile_read(
        oa.TrueNode(),
        bound_model(COMPOSED_BEAST),
        POSTGRES,
        target(COMPOSED_BEAST, "Beast"),
    )
    narrowed = compile_read(
        oa.TrueNode(),
        bound_model(COMPOSED_BEAST),
        POSTGRES,
        target(COMPOSED_BEAST, "Beast"),
        narrow_to=_narrow(COMPOSED_BEAST, "Wolf"),
    )

    assert (
        broad.statement.sql
        == "select t0.id, t0.kind, t0.name, t0.keeper_id, t0.howl from px.beast t0"
    )
    assert narrowed.statement.sql.endswith("from px.beast t0 where t0.kind = ?")
    assert narrowed.statement.binds == ("wolf",)


def test_a_partially_composed_document_root_read_stays_unpartitioned_and_unfiltered() -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(COMPOSED_DOCUMENT_BEAST),
        POSTGRES,
        target(COMPOSED_DOCUMENT_BEAST, "Beast"),
        result_form="instance",
    )

    assert compiled.statement.sql == (
        "select t0.id, t0.kind, t0.leader_id, not t0.payload is null, t0.payload "
        "from px.beast_document t0"
    )
    (row,) = deliver(
        COMPOSED_DOCUMENT_BEAST,
        compiled,
        [{"id": 3, "kind": "bear", "leader_id": 1, "payload": {"name": "Bruno"}}],
    )
    assert row.entity == "Beast"
    assert row.issues == (("stored-data-family-tag-unknown", "bear"),)


def test_tph_row_tagged_outside_the_composed_family_is_refused_by_name() -> None:
    # A model may compose a family's concrete leaves PARTIALLY (m-inheritance), and
    # an untouched abstract-root read injects no tag predicate (m-sql), so the shared
    # table can hand back a row tagged for a sibling this model never composed. The
    # tag map is the composed family's, so that row maps to nothing, and it is
    # reported as `stored-data-family-tag-unknown` carrying the observed tag rather
    # than surfacing as a bare mapping miss.
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Beast",
        table="beast",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    wolf = Entity(
        name="Wolf",
        inheritance=Inheritance(role="concrete-subtype", parent="Beast", tag_value="wolf"),
        attributes=(Attribute(name="howl", type="string", column="howl", nullable=True),),
    )
    partial = formed(Metamodel(entities=(root, wolf)))
    compiled = compile_read(oa.TrueNode(), bound_model(partial), POSTGRES, target(partial, "Beast"))

    assert compiled.statement.sql == "select t0.id, t0.kind, t0.howl from px.beast t0"
    wolf, bear = deliver(
        partial,
        compiled,
        [{"id": 1, "kind": "wolf", "howl": "aooo"}, {"id": 2, "kind": "bear", "howl": None}],
    )
    assert (wolf.entity, wolf.issues) == ("Wolf", ())
    assert bear.issues == (("stored-data-family-tag-unknown", "bear"),)
    # That row resolves to the family ROOT, which no position holds — the root is
    # abstract and only concretes are projected — so `resolvable` is what tells a
    # consumer the Entity exists at all before a bear row proves it.
    beast = target(partial, "Beast").identity
    assert bear.entity == "Beast"
    assert beast not in compiled.resolved_position
    assert beast in compiled.result_contract.resolvable


def _own_column_occurrences() -> Any:
    """A table-per-hierarchy family whose concretes each own a Value Object Column.

    ``Barge`` and ``Tug`` are sibling concretes under the root ``Vessel``, and
    ``Barge`` sorts ahead of ``Tug``, so a read targeting the root resolves a
    position of two concretes whose first member is not the one a ``tug`` row
    names.
    """
    from parallax.descriptor._records import (
        Attribute,
        Entity,
        Inheritance,
        Metamodel,
        ValueObject,
        ValueObjectAttribute,
    )

    return formed(
        Metamodel(
            entities=(
                Entity(
                    name="Vessel",
                    table="vessel",
                    inheritance=Inheritance(
                        role="root", strategy="table-per-hierarchy", tag_column="kind"
                    ),
                    attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
                ),
                Entity(
                    name="Tug",
                    inheritance=Inheritance(
                        role="concrete-subtype", parent="Vessel", tag_value="tug"
                    ),
                    value_objects=(
                        ValueObject(
                            name="berth",
                            column="berth",
                            nullable=True,
                            attributes=(
                                ValueObjectAttribute(name="code", type="string", nullable=True),
                            ),
                        ),
                    ),
                ),
                Entity(
                    name="Barge",
                    inheritance=Inheritance(
                        role="concrete-subtype", parent="Vessel", tag_value="barge"
                    ),
                    value_objects=(
                        ValueObject(
                            name="deck",
                            column="deck",
                            nullable=True,
                            attributes=(
                                ValueObjectAttribute(name="area", type="string", nullable=True),
                            ),
                        ),
                    ),
                ),
            )
        )
    )


def test_own_column_occurrences_are_classified_for_the_concrete_the_row_names() -> None:
    # An abstract target over several concretes projects the position's whole
    # superset, so a row carries its siblings' occurrence Columns as null. What is
    # classified is the RESOLVED concrete's own occurrences — the tag names a
    # `Tug` row, so `Tug`'s `berth` is decoded, while `Barge`'s stored `deck` is
    # no member of that row.
    meta = _own_column_occurrences()
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(meta),
        POSTGRES,
        target(meta, "Vessel"),
        result_form="instance",
    )
    assert compiled.resolved_position == (
        target(meta, "Barge").identity,
        target(meta, "Tug").identity,
    )
    (tug,) = deliver(
        meta,
        compiled,
        [{"id": 1, "kind": "tug", "berth": {"code": "A1"}, "deck": {"area": "9"}}],
    )
    assert (tug.entity, tug.issues) == ("Tug", ())
    assert tug.members == {"id": 1, "berth": {"code": "A1"}}


def test_a_tpcs_union_lands_its_document_tier_under_one_row_key() -> None:
    # Storage Layout is root-owned, so every branch of a family spells the shared
    # Structured Column the way the root declared it, and the union projects that
    # tier under one result alias whichever branch rendered the row. One column
    # for the whole read rests on exactly that, and both branches read through it.
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Publication"),
        result_form="instance",
    )
    assert compiled.statement.sql == (
        "select t0.id, not t0.payload is null, t0.payload, 'Book' family_variant "
        "from px.publication_book t0 union all "
        "select t0.id, not t0.payload is null, t0.payload, 'Film' family_variant "
        "from px.publication_film t0"
    )
    shared = compiled.result_contract.shared_document
    assert shared is not None and shared.column == "payload"
    book, film = deliver(
        DOCUMENT_LAYOUT,
        compiled,
        [
            {"id": 1, "payload": {"title": "Systems", "pages": 320}, "family_variant": "Book"},
            {"id": 1, "payload": {"title": "Systems", "minutes": 320}, "family_variant": "Film"},
        ],
    )
    assert (book.entity, book.members["pages"]) == ("Book", 320)
    assert (film.entity, film.members["minutes"]) == ("Film", 320)
    assert all("payload" not in row.members for row in (book, film))


def test_tpcs_union_preserves_qualified_duplicate_variant_identities() -> None:
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Record",
        namespace="catalog",
        inheritance=Inheritance(role="root", strategy="table-per-concrete-subtype"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    archive = Entity(
        name="SharedVariant",
        namespace="archive",
        table="archive_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="archiveLabel", type="string", column="shared_label"),),
    )
    catalog = Entity(
        name="SharedVariant",
        namespace="catalog",
        table="catalog_shared",
        inheritance=Inheritance(role="concrete-subtype", parent="catalog.Record"),
        attributes=(Attribute(name="catalogLabel", type="string", column="shared_label"),),
    )
    meta = formed(Metamodel(entities=(root, archive, catalog)))
    root_metadata = meta.entity(EntityIdentity("catalog", "Record"))
    assert root_metadata is not None

    compiled = compile_read(oa.TrueNode(), bound_model(meta), POSTGRES, root_metadata)

    assert compiled.statement.sql == (
        "select t0.id, t0.shared_label parallax_attr_0, cast(null as text) "
        "parallax_attr_1, 'archive.SharedVariant' family_variant from px.archive_shared t0 "
        "union all select t0.id, cast(null as text) parallax_attr_0, t0.shared_label "
        "parallax_attr_1, 'catalog.SharedVariant' family_variant from px.catalog_shared t0"
    )
    (row,) = deliver(
        meta,
        compiled,
        [
            {
                "id": 1,
                "parallax_attr_0": "archived",
                "parallax_attr_1": None,
                "family_variant": "archive.SharedVariant",
            }
        ],
    )
    assert (row.entity, row.issues) == ("SharedVariant", ())
    assert row.members == {"id": 1, "archiveLabel": "archived"}


def test_tpcs_narrow_to_a_single_concrete_carries_no_family_variant() -> None:
    # The settled asymmetry with table-per-hierarchy (m-sql, explicit): a single
    # resolved concrete has no shared table to discriminate and no sibling branch
    # to distinguish it from, so it projects no variant carrier.
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "Document"),
        narrow_to=_narrow(DOCUMENT, "Invoice"),
    )
    assert "family_variant" not in compiled.statement.sql
    assert compiled.read_shape.variant == "single-table"
    assert tuple(root.mapping_owner for root in compiled.read_shape.roots) == _narrow(
        DOCUMENT, "Invoice"
    )
    assert not compiled.read_shape.may_repeat_row_keys
    assert not compiled.result_contract.may_repeat_row_keys
    # Nothing discriminates, so every row of this read names the one concrete and
    # `resolvable` collapses to it — the fixed identity is the whole set.
    assert compiled.result_contract.resolvable == (target(DOCUMENT, "Invoice").identity,)


# --------------------------------------------------------------------------- #
# `CompiledRead.narrow_to`: the root-level authored-narrow a converted row     #
# resolves its own concrete identity through, where a deep-fetch child level   #
# takes its own `QueryFetchStep.narrow_to` instead. It reports the AUTHORED   #
# selection, not the resolved effective set — resolution belongs to            #
# materialization, which knows the row.                                        #
# --------------------------------------------------------------------------- #
def test_narrow_to_is_none_for_a_bare_read() -> None:
    assert (
        compile_read(
            oa.TrueNode(),
            bound_model(DOCUMENT),
            POSTGRES,
            target(DOCUMENT, "Document"),
        ).narrow_to
        is None
    )


def test_narrow_to_carries_a_top_level_narrows_authored_subtypes() -> None:
    invoice = target(DOCUMENT, "Invoice").identity
    assert compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "Document"),
        narrow_to=(invoice,),
    ).narrow_to == (invoice,)


def test_narrow_to_is_independent_of_result_shape_fields() -> None:
    narrowed = _narrow(ANIMAL, "Cat", "Dog")
    assert (
        compile_read(
            oa.TrueNode(),
            bound_model(ANIMAL),
            POSTGRES,
            target(ANIMAL, "Animal"),
            narrow_to=narrowed,
            limit=1,
        ).narrow_to
        == narrowed
    )


def test_a_mid_predicate_narrow_is_not_the_reads_own_narrow() -> None:
    # Only a TOP-LEVEL narrow sets the read's position; one nested inside
    # and/or/not/group is a local branch guard and must not leak into `narrow_to`.
    op = oa.Or(
        operands=(
            oa.Narrow(
                to=("Dog",),
                operand=oa.Comparison(
                    op="greaterThan", subject=oa.FieldSubject("Dog.barkVolume"), value=5
                ),
            ),
            oa.Narrow(
                to=("Cat",),
                operand=oa.Comparison(op="eq", subject=oa.FieldSubject("Cat.indoor"), value=True),
            ),
        )
    )
    assert (
        compile_read(op, bound_model(ANIMAL), POSTGRES, target(ANIMAL, "Animal")).narrow_to is None
    )


def test_family_attribute_resolution_spans_the_roots_projection_superset() -> None:
    # A predicate resolves an attribute reference against the whole family, which
    # is the family root's projection superset: the ancestry prefix plus every
    # concrete's own block. An abstract position with no concrete descendant
    # contributes to no such block, so its own attributes are unreachable — a
    # position no valid read can name, since narrowing to it resolves to the
    # empty set.
    from parallax.descriptor._records import Attribute, Entity, Inheritance, Metamodel

    root = Entity(
        name="Root",
        table="root_tbl",
        inheritance=Inheritance(role="root", strategy="table-per-hierarchy", tag_column="kind"),
        attributes=(Attribute(name="id", type="int64", column="id", primary_key=True),),
    )
    leaf = Entity(
        name="Leaf",
        inheritance=Inheritance(role="concrete-subtype", parent="Root", tag_value="leaf"),
        attributes=(Attribute(name="x", type="int32", column="x"),),
    )
    barren = Entity(
        name="Barren",
        inheritance=Inheritance(role="abstract-subtype", parent="Root"),
        attributes=(Attribute(name="y", type="int32", column="y"),),
    )
    meta = formed(Metamodel(entities=(root, leaf, barren)))

    # The root's own and the concrete's own both resolve from the concrete target.
    compiled = compile_read(
        oa.Comparison(op="eq", subject=oa.FieldSubject("Root.id"), value=1),
        bound_model(meta),
        POSTGRES,
        target(meta, "Leaf"),
    )
    assert compiled.statement.sql.endswith("where t0.id = ? and t0.kind = ?")
    with raises_code(UsageError, "subtype-attribute-outside-narrow-scope"):
        compile_read(
            oa.Comparison(op="eq", subject=oa.FieldSubject("Barren.y"), value=1),
            bound_model(meta),
            POSTGRES,
            target(meta, "Leaf"),
        )


# --------------------------------------------------------------------------- #
# The union's result-shape tail (m-sql "Inheritance — table-per-concrete-      #
# subtype lowering"). The two goldened witnesses are m-inheritance-134 / -135; #
# these pin the seams a golden over `document.yaml` cannot reach, because that #
# family's contributors neither collide nor live inside a document.            #
# --------------------------------------------------------------------------- #
def test_tpcs_union_refuses_only_a_requested_shared_lock() -> None:
    # A participating read of a versioned family requests no shared lock, so its
    # union compiles. A requested lock refuses: PostgreSQL grants one over neither
    # a `UNION` result nor any input of one, and it cannot be silently dropped
    # because it is what licenses a later ungated write. An unversioned family
    # requests it under either preference.
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(APPLIANCE),
        POSTGRES,
        target(APPLIANCE, "Appliance"),
        preference="optimistic",
    )
    assert " union all " in compiled.statement.sql
    assert compiled.read_shape.variant == "tpcs-union"
    assert compiled.read_shape.is_union
    assert len(compiled.read_shape.roots) > 1
    assert all(root.mapping_owner == root.concrete for root in compiled.read_shape.roots)
    assert compiled.read_shape.may_repeat_row_keys
    assert compiled.result_contract.may_repeat_row_keys
    assert "for share" not in compiled.statement.sql
    with raises_code(UnsupportedError, INHERITANCE_LOCKING_READ_UNSUPPORTED) as refused:
        compile_read(
            oa.TrueNode(),
            bound_model(DOCUMENT),
            POSTGRES,
            target(DOCUMENT, "Document"),
            preference="locking",
        )
    # The refusal names a current limitation and the ways around it, never a defect.
    assert "this version of Parallax cannot lock" in str(refused.value)
    assert "Version the family root, read one concrete subtype, or read without the lock" in str(
        refused.value
    )


def test_tpcs_union_orders_by_the_collision_safe_result_alias() -> None:
    # A contributor whose physical spelling is the synthetic `family_variant`
    # carrier reaches the union only through its allocated internal alias, so
    # ordering by it must name the alias — `u.family_variant` would order by the
    # variant literal instead, silently answering a different query.
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(MATERIALIZATION_KEYS),
        POSTGRES,
        target(MATERIALIZATION_KEYS, "Record"),
        order_by=(oq.OrderKey(attr="catalog.Record.variantMarker", direction="asc"),),
    )
    assert compiled.statement.sql.endswith(") u order by u.parallax_attr_1 asc")
    assert "t0.family_variant parallax_attr_1" in compiled.statement.sql


def test_tpcs_tuple_rows_read_branch_values_through_collision_safe_aliases() -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(MATERIALIZATION_KEYS),
        POSTGRES,
        target(MATERIALIZATION_KEYS, "Record"),
        result_form="instance",
    )
    archive, catalog = deliver(
        MATERIALIZATION_KEYS,
        compiled,
        [
            {
                "id": 3,
                "parallax_attr_1": "archive-marker",
                "parallax_attr_2": "archived",
                "parallax_attr_3": None,
                "family_variant": "archive.SharedVariant",
            },
            {
                "id": 4,
                "parallax_attr_1": "catalog-marker",
                "parallax_attr_2": None,
                "parallax_attr_3": "catalogued",
                "family_variant": "catalog.SharedVariant",
            },
        ],
    )

    assert [row.members for row in (archive, catalog)] == [
        {"id": 3, "variantMarker": "archive-marker", "archiveLabel": "archived"},
        {"id": 4, "variantMarker": "catalog-marker", "catalogLabel": "catalogued"},
    ]


def test_tpcs_union_orders_a_document_resident_key_through_the_union_alias() -> None:
    # Under a Relational Document Layout the ordering key has no Column of its
    # own, so the term is the dialect's extraction over the ONE Structured Column
    # the union projects. Its path bind lands on the outer statement, after every
    # branch bind and before the cap's. The wrapped branches project the document
    # as a single aliased cell and the outer select expands the read pair.
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT_LAYOUT),
        POSTGRES,
        target(DOCUMENT_LAYOUT, "Publication"),
        order_by=(oq.OrderKey(attr="parallax.compatibility.Publication.title", direction="desc"),),
        limit=2,
        result_form="instance",
    )
    assert compiled.statement.sql == (
        "select u.id, not u.payload is null, u.payload, u.family_variant from ("
        "select t0.id, t0.payload, 'Book' family_variant from px.publication_book t0 union all "
        "select t0.id, t0.payload, 'Film' family_variant from px.publication_film t0) u "
        "order by jsonb_extract_path_text(u.payload, ?) desc limit ?"
    )
    assert compiled.statement.binds == ("title", 2)
    assert compiled.document_reads == ((1, 2),)


_WRAPPED_TPCS_ROWS: dict[str, tuple[dict[str, object], ...]] = {
    # Spelled by the union's result aliases; the outer select reads each through.
    "columns": (
        {
            "id": 1,
            "holder_id": 10,
            "digest": "0a0b",
            "origin": {"city": "Rome"},
            "parallax_attr_0": {"city": "Lyon"},
            "family_variant": "Left",
        },
        {
            "id": 2,
            "holder_id": None,
            "digest": None,
            "note": "memo",
            "tags": ["a"],
            "origin": StructuredDocument(None),
            "family_variant": "Plain",
        },
        {
            "id": 3,
            "holder_id": 30,
            "digest": "ff",
            "parallax_attr_1": None,
            "family_variant": "Right",
        },
    ),
    "document": (
        {
            "id": 1,
            "holder_id": 10,
            "payload": {"origin": {"city": "Rome"}, "home": {"city": "Lyon"}},
            "family_variant": "Left",
        },
        {
            "id": 2,
            "holder_id": None,
            "payload": {"note": "memo", "tags": ["a"], "origin": None},
            "family_variant": "Plain",
        },
        {"id": 3, "holder_id": 30, "payload": None, "family_variant": "Right"},
    ),
}


def _wrapped_tpcs_delivery(
    layout: support.Layout, form: Literal["row", "instance"]
) -> list[tuple[str, dict[str, object]]]:
    """Each delivered row as (Entity, members). An instance-form read fetches every
    occurrence and narrows to the fields its branch owns."""
    instance = form == "instance"
    columns = layout == "columns"
    left_occurrences = {"origin": {"city": "Rome"}, "home": {"city": "Lyon"}} if instance else {}
    plain_occurrences = {"origin": None} if instance else {}
    right_occurrences = {"origin": None, "home": None} if instance else {}

    def digest(value: bytes | None) -> dict[str, object]:
        return {"digest": value} if columns else {}

    return [
        ("Left", {"id": 1, "holderId": 10, **digest(b"\x0a\x0b"), **left_occurrences}),
        (
            "Plain",
            {
                "id": 2,
                "holderId": None,
                **digest(None),
                "note": "memo",
                "tags": ("a",),
                **plain_occurrences,
            },
        ),
        ("Right", {"id": 3, "holderId": 30, **digest(b"\xff"), **right_occurrences}),
    ]


@pytest.mark.parametrize("form", ["row", "instance"])
@pytest.mark.parametrize("layout", support.LAYOUTS)
def test_a_wrapped_tpcs_union_delivers_through_its_outer_select(
    layout: support.Layout, form: Literal["row", "instance"]
) -> None:
    # An ordered, limited union selects every result alias through the derived
    # table and expands each document pair there, so the encoded Bytes cell, the
    # collision-safe sibling aliases, and the variant literal all reach delivery
    # through `u`.
    namespace = f"read.projection.matrix.tpcs.{layout}"
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(support.MATRIX_META),
        POSTGRES,
        support.matrix_entity("tpcs", layout, "Root"),
        order_by=(oq.OrderKey(attr=f"{namespace}.Root.holderId", direction="desc"),),
        limit=3,
        result_form=form,
    )
    outer = {
        ("columns", "row"): "u.id, u.holder_id, u.digest, u.note, not u.tags is null, u.tags",
        ("columns", "instance"): (
            "u.id, u.holder_id, u.digest, u.note, not u.tags is null, u.tags, "
            "not u.origin is null, u.origin, not u.parallax_attr_0 is null, u.parallax_attr_0, "
            "not u.parallax_attr_1 is null, u.parallax_attr_1"
        ),
        ("document", "row"): "u.id, u.holder_id, not u.payload is null, u.payload",
        ("document", "instance"): "u.id, u.holder_id, not u.payload is null, u.payload",
    }[layout, form]
    assert compiled.statement.sql.startswith(f"select {outer}, u.family_variant from (select ")
    assert compiled.statement.sql.endswith(") u order by u.holder_id desc nulls last limit ?")
    rows = [
        {key: value for key, value in row.items() if f"u.{key}" in compiled.statement.sql}
        for row in _WRAPPED_TPCS_ROWS[layout]
    ]

    delivered = deliver(support.MATRIX_META, compiled, rows)

    assert [(row.entity, row.members) for row in delivered] == (
        _wrapped_tpcs_delivery(layout, form)
    )
    assert all(row.issues == () for row in delivered)
    if layout == "document":
        assert [row.document for row in delivered] == [
            {"origin": {"city": "Rome"}, "home": {"city": "Lyon"}},
            {"note": "memo", "tags": ["a"], "origin": None},
            None,
        ]


def test_tpcs_union_projects_a_top_level_occurrence_for_the_instance_form_alone() -> None:
    # `m-sql` *Read projection* rule 3: a top-level Value Object occurrence's own
    # `Document` slot reaches an instance-form read and no row-form one. Under
    # `Columns` layout only the concrete that DECLARES the occurrence carries the
    # Structured Column, so the owning branch projects the document read pair and
    # each sibling branch the typed `NULL` placeholder under the same result alias.
    instance = compile_read(
        oa.TrueNode(),
        bound_model(DOCUMENT),
        POSTGRES,
        target(DOCUMENT, "Document"),
        result_form="instance",
    )
    assert (
        "not t0.annotation is null, t0.annotation, 'Memo' family_variant"
    ) in instance.statement.sql
    assert instance.statement.sql.count("false, cast(null as jsonb) annotation") == 2
    assert instance.document_reads == ((7, 8),)

    row_form = compile_read(
        oa.TrueNode(), bound_model(DOCUMENT), POSTGRES, target(DOCUMENT, "Document")
    )
    assert "annotation" not in row_form.statement.sql
    assert row_form.document_reads == ()


# --------------------------------------------------------------------------- #
# A row-form family-member read fetches exactly its explicit demand.           #
# --------------------------------------------------------------------------- #
_FAMILY_META = model_of(family.MODEL)
_LATEST: dict[TemporalDimension, oq.TemporalSelection] = {
    "valid-time": oq.AsOf("latest"),
    "transaction-time": oq.AsOf("latest"),
}
_SCALARS = "t0.id, t0.from_z, t0.thru_z, t0.in_z, t0.out_z"
_HOLDING_SCALARS = "t0.id, t0.name, t0.from_z, t0.thru_z, t0.in_z, t0.out_z"
_PAYLOAD = "not t0.payload is null, t0.payload"


def _family_source(strategy: family.Strategy, layout: family.Layout, member: str) -> str:
    if strategy == "tph":
        return f" from px.fp_tph_{layout} t0 where t0.thru_z = ? and t0.out_z = ? and t0.kind = ?"
    return f" from px.fp_tpcs_{layout}_{member.lower()} t0 where t0.thru_z = ? and t0.out_z = ?"


def _widened(
    strategy: family.Strategy,
    layout: family.Layout,
    member: family.Member,
) -> Any:
    return compile_projected_read(
        oa.TrueNode(),
        _FAMILY_META,
        POSTGRES,
        family.member_metadata(strategy, layout, member),
        value_objects="all",
        observe_structured_document=True,
        temporal=_LATEST,
    )


def _fetched(compiled: Any) -> list[str]:
    return [member.identity.path[-1] for member in compiled.projection.value_objects]


def _fanned_out(compiled: Any) -> list[str] | None:
    shared = compiled.result_contract.shared_document
    if shared is None:
        return None
    ((_identity, fan_out),) = shared.per_entity
    return [key for key, _path in fan_out.members]


_WIDENED_SELECTS: dict[tuple[family.Layout, family.Member], str] = {
    ("columns", "Holding"): (
        f"{_HOLDING_SCALARS}, not t0.origin is null, t0.origin, not t0.home is null, t0.home, "
        "not t0.extra is null, t0.extra"
    ),
    ("columns", "Vault"): (
        f"{_SCALARS}, not t0.origin is null, t0.origin, not t0.deposit is null, t0.deposit"
    ),
    ("columns", "Bare"): _SCALARS,
    ("document", "Holding"): f"{_SCALARS}, {_PAYLOAD}",
    ("document", "Vault"): f"{_SCALARS}, {_PAYLOAD}",
    ("document", "Bare"): f"{_SCALARS}, {_PAYLOAD}",
}
_WIDENED_FAN_OUTS: dict[family.Member, list[str]] = {
    "Holding": ["name", "origin", "home", "extra"],
    "Vault": ["origin", "deposit"],
    "Bare": [],
}
_WIDENED_FETCHES: dict[family.Member, list[str]] = {
    "Holding": ["origin", "home", "extra"],
    "Vault": ["origin", "deposit"],
    "Bare": [],
}


@family.FAMILY_AXES
@pytest.mark.parametrize("member", family.MEMBERS)
def test_a_widened_row_read_of_a_family_member_fetches_every_value_object_and_its_document(
    strategy: family.Strategy, layout: family.Layout, member: family.Member
) -> None:
    compiled = _widened(strategy, layout, member)
    assert compiled.statement.sql == (
        f"select {_WIDENED_SELECTS[(layout, member)]}{_family_source(strategy, layout, member)}"
    )
    assert _fetched(compiled) == _WIDENED_FETCHES[member]
    assert _fanned_out(compiled) == (_WIDENED_FAN_OUTS[member] if layout == "document" else None)


@family.FAMILY_AXES
@pytest.mark.parametrize("member", family.MEMBERS)
def test_an_ordinary_row_read_of_a_family_member_fetches_no_value_object(
    strategy: family.Strategy, layout: family.Layout, member: family.Member
) -> None:
    compiled = compile_read(
        oa.TrueNode(),
        bound_model(_FAMILY_META),
        POSTGRES,
        family.member_metadata(strategy, layout, member),
        temporal=_LATEST,
    )
    resident = layout == "document" and member == "Holding"
    scalars = _HOLDING_SCALARS if member == "Holding" and layout == "columns" else _SCALARS
    select = f"{scalars}, {_PAYLOAD}" if resident else scalars
    assert compiled.statement.sql == f"select {select}{_family_source(strategy, layout, member)}"
    assert _fetched(compiled) == []
    assert _fanned_out(compiled) == (["name"] if resident else None)


# --------------------------------------------------------------------------- #
# A result contract refuses carriers its cells cannot back.                    #
# --------------------------------------------------------------------------- #
def _contract(meta: Metamodel, name: str, **options: Any) -> ReadResultContract:
    return compile_read(
        oa.TrueNode(), bound_model(meta), POSTGRES, target(meta, name), **options
    ).result_contract


def test_a_tagged_result_contract_requires_its_row_identity_carrier() -> None:
    tagged = _contract(ANIMAL, "Animal")
    assert tagged.identity_ordinal == 1
    with pytest.raises(ValueError, match="row identity carrier is required"):
        replace(tagged, identity_ordinal=None)


def test_a_fixed_identity_refuses_an_identity_carrier() -> None:
    # A page of one concrete names its rows when compiled; its capture cell is
    # a carrier no identity may claim instead.
    entity = target(ANIMAL, "Dog")
    plan = continuation.plan(
        oq.validate_object_query(entity, oq.object_query(entity.identity, oa.TrueNode()), ANIMAL),
        ANIMAL,
    )
    paged = compile_nonempty_read(
        read_planning.plan(
            plan.first(limit=2),
            ANIMAL,
            projection=read_planning.ReadProjectionRequest("none", False),
        ).root,
        ANIMAL,
        POSTGRES,
    ).result_contract
    (coordinate,) = paged.coordinate_ordinals
    with pytest.raises(ValueError, match="row identity carrier is required"):
        replace(paged, identity_ordinal=coordinate, coordinate_ordinals=())


def test_a_result_contract_refuses_a_shared_document_it_carries_no_cell_for() -> None:
    contract = _contract(DOCUMENT_LAYOUT, "Publication", result_form="instance")
    assert contract.shared_document is not None
    with pytest.raises(ValueError, match="shared document carrier is required"):
        replace(contract, shared_document_ordinal=None)
