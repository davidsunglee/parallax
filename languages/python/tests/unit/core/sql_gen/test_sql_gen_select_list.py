"""The select-list owner: what one emitted list yields, and the result contract
its cells must agree with the read's plan to build.

Rendering cases emit through the owner directly. Refusal cases drive the real
compiler and disturb one planning or emission step with a test-local wrapper, so
the refusal is the one contract construction raises for a select list that
disagrees with what its read planned.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from parallax.core import continuation, deep_fetch
from parallax.core import predicate as oa
from parallax.core.base import STRING
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import AttributeIdentity, EntityIdentity
from parallax.core.object_query import AsOf, object_query, validate_object_query
from parallax.core.object_query._resolved import ContinuationCoordinate
from parallax.core.sql_gen import SqlGenError
from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.sql_gen._compile import compile_read as compile_entity_query
from parallax.core.sql_gen._inheritance import (
    ProjectedColumn,
    SingleTableReadPlan,
    TpcsUnionBranchColumn,
)
from parallax.core.sql_gen._select_list import SelectListBuilder
from parallax.core.storage_layout import RelationalDocument
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model, target
from tests.unit.core.sql_gen._plan_reuse_support import reaches_compilation_state

ORDERS = model("orders")
ANIMAL = model("animal")
DOCUMENT = model("document")
DOCUMENT_LAYOUT = model("document-layout")

_FIRST = EntityIdentity(None, "First")
_SECOND = EntityIdentity(None, "Second")


def _documents() -> tuple[TpcsUnionBranchColumn, TpcsUnionBranchColumn]:
    """One branch's owned document slot beside its sibling's, each under the
    alias the union allocated."""
    return (
        TpcsUnionBranchColumn(
            RelationalDocument(_FIRST), "first_payload", None, None, True, "payload", document=True
        ),
        TpcsUnionBranchColumn(
            RelationalDocument(_SECOND),
            "second_payload",
            None,
            None,
            False,
            "other_payload",
            document=True,
        ),
    )


def _branch(*, document_pairs: bool) -> SelectListBuilder:
    branch = SelectListBuilder(POSTGRES, document_pairs=document_pairs)
    for column in _documents():
        branch.emit_branch(column, table_alias="t0")
    branch.emit_variant("First")
    return branch


def test_union_document_branches_alias_owned_cells_and_type_absent_cells() -> None:
    branch = _branch(document_pairs=True)
    assert branch.sql == (
        "not t0.first_payload is null, t0.first_payload payload, false, "
        "cast(null as jsonb) other_payload, 'First' family_variant"
    )
    assert branch.binds == ()
    assert branch.document_reads == ((0, 1), (2, 3))


def test_union_document_branches_omit_the_presence_cell_under_a_wrapped_union() -> None:
    # A presence cell carries no result alias, so it cannot be addressed from
    # outside a derived table; a wrapped union leaves the document slot a single
    # aliased cell per branch and the outer select expands the pair.
    branch = _branch(document_pairs=False)
    assert branch.sql == (
        "t0.first_payload payload, cast(null as jsonb) other_payload, 'First' family_variant"
    )
    assert branch.document_reads == ()
    outer = branch.select_through("u")
    assert outer.sql == (
        "not u.payload is null, u.payload, not u.other_payload is null, u.other_payload, "
        "u.family_variant"
    )
    assert outer.document_reads == ((0, 1), (2, 3))


def test_two_lists_disagreeing_on_their_cells_are_refused() -> None:
    owner = AttributeIdentity(_FIRST, "label")
    first = SelectListBuilder(POSTGRES)
    first.emit(ProjectedColumn(owner, "label", STRING), table_alias="t0")
    longer = SelectListBuilder(POSTGRES)
    longer.emit(ProjectedColumn(owner, "label", STRING), table_alias="p1")
    longer.emit_variant("First")
    renamed = SelectListBuilder(POSTGRES)
    renamed.emit(ProjectedColumn(owner, "title", STRING), table_alias="t0")

    first.require_agreement(first)
    with pytest.raises(SqlGenError, match="disagree on their cells"):
        first.require_agreement(longer)
    with pytest.raises(SqlGenError, match="disagree on the cell 'label'"):
        first.require_agreement(renamed)


def test_a_contributor_no_scalar_cell_carries_is_refused_by_name() -> None:
    select_list = SelectListBuilder(POSTGRES)
    select_list.emit_variant("First")
    with pytest.raises(SqlGenError, match="has no scalar cell"):
        select_list.selected_scalar(AttributeIdentity(_FIRST, "id"))


def test_no_compiled_read_retains_the_select_list_it_was_built_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[SelectListBuilder] = []
    real = SelectListBuilder.result_contract

    def recording(self: SelectListBuilder, *args: Any, **kwargs: Any) -> Any:
        built.append(self)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(SelectListBuilder, "result_contract", recording)
    compiled = compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))

    (select_list,) = built
    assert reaches_compilation_state(select_list)
    assert not reaches_compilation_state(compiled)


# --------------------------------------------------------------------------- #
# Construction refuses a select list that disagrees with what its read planned. #
# --------------------------------------------------------------------------- #
def _continuing(limit: int = 2) -> CompiledRead:
    """A continuing page of `Order` by key: an ordinary arm and a NULL-tail arm."""
    entity = target(ORDERS, "Order")
    plan = continuation.plan(
        validate_object_query(entity, object_query(entity.identity, oa.TrueNode()), ORDERS),
        ORDERS,
    )
    return compile_entity_query(
        deep_fetch.plan(
            plan.after(ContinuationCoordinate((1,)), limit=limit),
            ORDERS,
            projection=deep_fetch.ReadProjectionRequest("none", False),
        ).root,
        ORDERS,
        POSTGRES,
    )


def test_a_continuing_page_compiles_its_two_arms_through_one_select_list() -> None:
    assert ") union all (select " in _continuing().statement.sql


def test_union_branches_selecting_different_cells_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variants: list[str] = []
    real = SelectListBuilder.emit_variant

    def doubled_after_the_first_branch(self: SelectListBuilder, variant: str) -> None:
        real(self, variant)
        if variants:
            real(self, variant)
        variants.append(variant)

    monkeypatch.setattr(SelectListBuilder, "emit_variant", doubled_after_the_first_branch)
    with pytest.raises(SqlGenError, match="disagree on their cells"):
        compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))


def test_union_branches_naming_one_contributor_differently_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emitted: list[TpcsUnionBranchColumn] = []
    real = SelectListBuilder.emit_branch

    def renamed_in_a_later_branch(
        self: SelectListBuilder, column: TpcsUnionBranchColumn, *, table_alias: str
    ) -> None:
        again = any(earlier.result_alias == column.result_alias for earlier in emitted)
        emitted.append(column)
        real(
            self,
            replace(column, result_alias=f"{column.result_alias}_again") if again else column,
            table_alias=table_alias,
        )

    monkeypatch.setattr(SelectListBuilder, "emit_branch", renamed_in_a_later_branch)
    with pytest.raises(SqlGenError, match="disagree on the cell 'id'"):
        compile_read(oa.TrueNode(), DOCUMENT, POSTGRES, target(DOCUMENT, "Document"))


def test_a_null_tail_arm_selecting_other_cells_than_the_ordinary_arm_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = vars(sql_compile)["_render_read_arm"]

    def widened_tail(*args: Any, **kwargs: Any) -> Any:
        statement, select_list = real(*args, **kwargs)
        if kwargs["null_tail"]:
            select_list.emit_variant("Order")
        return statement, select_list

    monkeypatch.setattr(sql_compile, "_render_read_arm", widened_tail)
    with pytest.raises(SqlGenError, match="disagree on their cells"):
        _continuing()


def test_a_page_capturing_no_coordinate_for_its_ordering_terms_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def captured_nothing(*args: object) -> None:
        del args

    monkeypatch.setattr(sql_compile, "_emit_coordinates", captured_nothing)
    with pytest.raises(SqlGenError, match="does not capture its ordering terms"):
        _continuing()


def _without_column(
    monkeypatch: pytest.MonkeyPatch, dropped: Callable[[ProjectedColumn], bool]
) -> None:
    """Plan every single-Table read without the column ``dropped`` selects."""
    real = vars(sql_compile)["_plan_read_shape"]

    def planned(*args: Any, **kwargs: Any) -> Any:
        shape = real(*args, **kwargs)
        assert isinstance(shape, SingleTableReadPlan)
        return replace(
            shape, columns=tuple(column for column in shape.columns if not dropped(column))
        )

    monkeypatch.setattr(sql_compile, "_plan_read_shape", planned)


def test_a_select_list_carrying_no_cell_for_a_fetched_member_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_column(monkeypatch, lambda column: column.column == "sku")
    with pytest.raises(SqlGenError, match="carries no source for the fetched member 'sku'"):
        compile_read(oa.TrueNode(), ORDERS, POSTGRES, target(ORDERS, "Order"))


def test_a_select_list_carrying_no_tag_for_a_tagged_read_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_column(monkeypatch, lambda column: column.column == "kind")
    with pytest.raises(ValueError, match="row identity carrier is required"):
        compile_read(oa.TrueNode(), ANIMAL, POSTGRES, target(ANIMAL, "Animal"))


def test_a_select_list_carrying_no_planned_shared_document_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _without_column(monkeypatch, lambda column: isinstance(column.contributor, RelationalDocument))
    with pytest.raises(SqlGenError, match="read without its shared document"):
        compile_read(
            oa.TrueNode(),
            DOCUMENT_LAYOUT,
            POSTGRES,
            target(DOCUMENT_LAYOUT, "Charter"),
            temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
        )
