"""Statement frontend spellings (python.md §2):
``.include(*paths)`` (deep-fetch, chained ``Rel[T]`` class access, hop-level
``.narrow()``), relationship ``.any()`` / ``.none()`` quantifiers, the
``Entity.narrow(...)`` constructor, and the statement-level ``.narrow(...)``
clause. Every example is validated immediately at build, against the model the
target's own hub sealed, never deferred to execution.

A deeper relationship hop is the one thing a path cannot answer for itself: it is
a model question, so it resolves through the Metamodel Binding the seeding class
access supplied. ``test_relationship_hops`` pins that resolution; here it is
exercised only as far as a multi-hop include needs it.
"""

from __future__ import annotations

import pytest

import inheritance_models as im
import snapshot_models as sm
from parallax.conformance.graph_models import Policy
from parallax.core import TX_TIME, UnsupportedFeatureError
from parallax.core.entity import RelationshipPath
from parallax.core.entity.statement import build_statement
from parallax.core.op_algebra import (
    All,
    DeepFetch,
    Exists,
    Limit,
    Narrow,
    NotExists,
    OperationRejectedError,
    PathSegment,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# .include(...) — deep-fetch path building.                                   #
# --------------------------------------------------------------------------- #
def test_single_hop_include_builds_a_deep_fetch_node() -> None:
    statement = sm.SnapOrder.where().include(sm.SnapOrder.items)
    op = statement.operation()
    assert isinstance(op, DeepFetch)
    assert op.paths == ((PathSegment(rel="SnapOrder.items"),),)


def test_multi_hop_include_resolves_the_deeper_hop_against_the_model() -> None:
    statement = sm.SnapOrder.where().include(sm.SnapOrder.items.statuses)
    op = statement.operation()
    assert isinstance(op, DeepFetch)
    assert op.paths == (
        (PathSegment(rel="SnapOrder.items"), PathSegment(rel="SnapOrderItem.statuses")),
    )


def test_a_deeper_hop_on_a_path_that_carries_no_model_is_refused() -> None:
    # A second hop is a model question, so a path built directly cannot answer it.
    bare = RelationshipPath(segments=(PathSegment(rel="SnapOrder.items"),), target="SnapOrderItem")
    with pytest.raises(AttributeError, match="resolves against the composed model"):
        _ = bare.statuses  # pyright: ignore[reportAttributeAccessIssue]


def test_a_deeper_hop_naming_no_declared_relationship_is_refused() -> None:
    with pytest.raises(AttributeError, match="declares no relationship"):
        _ = sm.SnapOrder.items.bogus_relationship  # pyright: ignore[reportAttributeAccessIssue]


def test_include_accumulates_across_calls() -> None:
    statement = sm.SnapOrder.where().include(sm.SnapOrder.items).include(sm.SnapOrder.statuses)
    op = statement.operation()
    assert isinstance(op, DeepFetch)
    assert len(op.paths) == 2


def test_include_with_no_paths_raises() -> None:
    with pytest.raises(ValueError, match="at least one path"):
        sm.SnapOrder.where().include()


def test_include_of_an_undeclared_relationship_raises_at_build() -> None:
    with pytest.raises(AttributeError, match="statuses"):
        sm.SnapOrderStatus.where().include(sm.SnapOrderStatus.statuses)  # type: ignore[attr-defined]


def test_relationship_path_dynamic_hop_rejects_a_private_name() -> None:
    with pytest.raises(AttributeError):
        sm.SnapOrder.items.__getattr__("_hidden")


def test_hop_narrow_derives_the_narrowed_view_path_segment() -> None:
    path = im.Folder.documents.narrow(im.Invoice, im.Receipt)
    assert path.segments[-1].rel == "Folder.documents"
    assert set(path.segments[-1].narrow) == {"Invoice", "Receipt"}


def test_include_of_a_narrowed_path_serializes_the_hop_narrow() -> None:
    statement = im.Folder.where().include(im.Folder.documents.narrow(im.Invoice))
    op = statement.operation()
    assert isinstance(op, DeepFetch)
    assert op.paths[0][0].narrow == ("Invoice",)


# --------------------------------------------------------------------------- #
# Relationship .any() / .none() quantifiers.                                  #
# --------------------------------------------------------------------------- #
def test_any_with_no_predicates_is_a_bare_existence_test() -> None:
    predicate = sm.SnapOrder.items.any()
    assert predicate.op == Exists(rel="SnapOrder.items", op=None)


def test_any_with_predicates_conjoins_the_interior() -> None:
    predicate = sm.SnapOrder.items.any(sm.SnapOrderItem.sku == "A")
    op = predicate.op
    assert isinstance(op, Exists)
    assert op.rel == "SnapOrder.items"


def test_none_builds_not_exists() -> None:
    predicate = sm.SnapOrder.items.none()
    assert predicate.op == NotExists(rel="SnapOrder.items", op=None)


def test_any_none_on_a_multi_hop_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="single relationship hop"):
        sm.SnapOrder.items.statuses.any()


def test_statement_with_any_validates_at_build() -> None:
    # Order.items.any(...) is a legal quantifier; the statement builds cleanly.
    statement = sm.SnapOrder.where(sm.SnapOrder.items.any(sm.SnapOrderItem.sku == "A"))
    assert statement.operation() is not None


def test_narrow_inside_a_relationship_scope_must_name_the_target_exactly() -> None:
    # Folder.documents targets Document (the family root); narrowing to a
    # concrete subtype inside the hop's own scope is legal.
    statement = im.Folder.where(
        im.Folder.documents.any(im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 0))
    )
    assert statement.operation() is not None


# --------------------------------------------------------------------------- #
# Entity.narrow(...) constructor + relationship-scope exact-naming.            #
# --------------------------------------------------------------------------- #
def test_narrow_constructor_builds_the_canonical_node() -> None:
    predicate = im.Document.narrow(im.Invoice, im.Receipt)
    assert predicate.op == Narrow(entity="Document", to=("Invoice", "Receipt"), operand=All())


def test_narrow_with_where_scopes_attribute_access_to_the_subtype() -> None:
    predicate = im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 100)
    op = predicate.op
    assert isinstance(op, Narrow)
    assert op.to == ("Invoice",)


def test_narrow_or_composition_of_two_branches_validates_at_where_build() -> None:
    statement = im.Document.where(
        im.Document.narrow(im.Invoice, where=im.Invoice.amount_due > 5)
        | im.Document.narrow(im.Receipt, where=im.Receipt.paid_amount > 5)
    )
    assert statement.operation() is not None


def test_narrow_broadening_outside_the_threaded_position_is_rejected() -> None:
    # FinancialDocument's effective set is {Invoice, Receipt}; nesting a
    # same-position narrow to Memo (outside it) must be rejected.
    with pytest.raises(OperationRejectedError) as caught:
        im.FinancialDocument.where(im.FinancialDocument.narrow(im.Memo))
    assert caught.value.rule == "narrow-outside-position"


# --------------------------------------------------------------------------- #
# The whole-statement .narrow(...) clause: single-shot, converges on the       #
# identical canonical node as the constructor form, grants no retroactive      #
# attribute scope to already-built `where` arguments.                         #
# --------------------------------------------------------------------------- #
def test_statement_level_narrow_wraps_the_conjoined_predicate() -> None:
    statement = im.Document.where().narrow(im.Invoice, im.Receipt)
    op = statement.operation()
    assert isinstance(op, Narrow)
    assert op.entity == "Document"
    assert op.to == ("Invoice", "Receipt")
    assert op.operand == All()


def test_statement_level_narrow_is_single_shot() -> None:
    statement = im.Document.where().narrow(im.Invoice)
    with pytest.raises(ValueError, match="single-shot"):
        statement.narrow(im.Receipt)


def test_clause_and_constructor_forms_converge_on_the_identical_node() -> None:
    via_clause = im.Document.where().narrow(im.Invoice).operation()
    via_constructor = im.Document.where(im.Document.narrow(im.Invoice)).operation()
    assert via_clause == via_constructor


def test_subtype_attribute_outside_narrow_scope_is_rejected_at_where_build_time() -> None:
    # The where() call itself validates immediately with the UNCONSTRAINED
    # position — a later `.narrow(...)` clause grants no retroactive scope.
    with pytest.raises(OperationRejectedError) as caught:
        im.Document.where(im.Invoice.amount_due > 3)
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


def test_a_statement_built_with_no_binding_states_no_model_rule_at_all() -> None:
    # The Binding is the model a build-time rule is stated over, so a statement
    # built without one carries the very predicate the bound `Document.where(...)`
    # above refuses. That is what lets the operation-shaping clauses be exercised
    # with no whole model behind them.
    out_of_scope = im.Invoice.amount_due > 3
    statement = build_statement("Document", (out_of_scope,))
    assert statement.binding is None
    assert statement.operation() == out_of_scope.op
    assert statement.limit(2).operation() == Limit(operand=out_of_scope.op, count=2)


def test_narrow_clause_after_an_out_of_scope_where_predicate_never_legalizes_it() -> None:
    # `.where(Invoice.amount_due > 3)` ALREADY raises before `.narrow(...)` is
    # even reached — the statement-level clause grants no retroactive scope.
    with pytest.raises(OperationRejectedError) as caught:
        im.Document.where(im.Invoice.amount_due > 3).narrow(im.Invoice)
    assert caught.value.rule == "subtype-attribute-outside-narrow-scope"


# --------------------------------------------------------------------------- #
# .history() / .as_of_range() + .include(...): the snapshot-history-includes  #
# deferral (spec §3) — UnsupportedFeatureError, distinct from a validation     #
# error, in both call orders.                                                 #
# --------------------------------------------------------------------------- #
def test_history_then_include_is_deferred() -> None:
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where().history(TX_TIME).include(Policy.coverages)


def test_include_then_history_is_deferred() -> None:
    with pytest.raises(UnsupportedFeatureError, match="snapshot-history-includes"):
        Policy.where().include(Policy.coverages).history(TX_TIME)
