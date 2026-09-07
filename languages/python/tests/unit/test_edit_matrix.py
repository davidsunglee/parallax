"""The shared edit derivation over both frontends, backings, and branches."""

from __future__ import annotations

from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from _compact_support import carries_instance_storage, published, raw_row

from _support import mirrored_models as mm
from parallax.conformance.edit_models import LEDGER, Note, NoteTag
from parallax.core import AbstractRoot, Attr, ConcreteSubtype, Entity, TablePerHierarchy, attr
from parallax.core.entity._instance_state import is_published
from parallax.core.entity._pydantic_storage import attach_instance_state

if TYPE_CHECKING:
    from collections.abc import Mapping


type Witness = Note | NoteTag

_SOURCES = (
    pytest.param(
        Note,
        {"id": 1, "title": "alpha"},
        "title",
        {"body": "revised"},
        id="entity",
    ),
    pytest.param(
        NoteTag,
        {"label": "a"},
        "label",
        {"weight": 1},
        id="value-object",
    ),
)

_BRANCHES = ("changed", "change-free")


def _memo_payload(members: Mapping[str, object]) -> list[str]:
    return [cast("str", members.get("title", members.get("label")))]


def _source(
    backing: str, cls: type[Witness], members: dict[str, object]
) -> tuple[Witness, list[str]]:
    memo = _memo_payload(members)
    if backing == "ordinary":
        value = cast("Witness", cast("Any", cls).model_construct(**members))
        attach_instance_state(value, "memo", memo)
    else:
        value = published(cls, **members)
        value.remember(memo)
    return value, memo


@pytest.mark.parametrize("backing", ["ordinary", "published"])
@pytest.mark.parametrize("branch", _BRANCHES)
@pytest.mark.parametrize(
    "cls, members, cache_member, authored_changes",
    _SOURCES,
)
def test_edit_carries_application_state_without_hooks_and_drops_derived_cache(
    backing: str,
    branch: str,
    cls: type[Witness],
    members: dict[str, object],
    cache_member: str,
    authored_changes: dict[str, object],
) -> None:
    LEDGER.reset()
    source, memo = _source(backing, cls, members)
    source_values = {name: getattr(source, name) for name in cls.model_fields}
    changes = authored_changes if branch == "changed" else {}
    expected_cache = cast("str", members[cache_member]).upper()
    assert source.shouted == expected_cache
    before = LEDGER.snapshot()

    result = source.edit(**changes)

    after_edit = LEDGER.snapshot()
    assert after_edit == before
    assert result.memo is memo
    assert source.memo is memo
    assert result.shouted == expected_cache
    after_result_cache = LEDGER.snapshot()
    assert after_result_cache.cache_evaluations == before.cache_evaluations + 1
    assert after_result_cache.hook_calls == before.hook_calls
    assert source.shouted == expected_cache
    assert LEDGER.snapshot() == after_result_cache
    assert {name: getattr(source, name) for name in cls.model_fields} == source_values
    assert all(getattr(result, name) == value for name, value in changes.items())

    memo.append("shared")
    assert source.memo == result.memo == [memo[0], "shared"]
    rebound = ["copy"]
    result.remember(rebound)
    assert result.memo is rebound
    assert source.memo is memo
    assert not is_published(result)
    assert raw_row(result) is None
    if backing == "published":
        assert is_published(source)
        assert not carries_instance_storage(source)


def test_a_published_framework_owned_member_bypasses_the_validating_constructor() -> None:
    source = published(
        mm.Account,
        id=1,
        owner="Ada",
        balance=Decimal("100.00"),
        version=3,
    )

    result = source.edit(balance=Decimal("125.00"))

    assert result.balance == Decimal("125.00")
    assert result.version == 3


def test_the_entity_witness_reports_direct_setter_dispatch() -> None:
    LEDGER.reset()
    value = Note.model_construct(id=1, title="alpha")

    object.__setattr__(value, "memo", ["assigned"])

    assert value.memo == ["intercepted"]
    assert LEDGER.snapshot().hook_calls == 1


class _CachedRoot(
    Entity,
    table="cached_root",
    namespace="parallax.edit_matrix",
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str]

    @cached_property
    def memo(self) -> object:
        return object()


class _PlainBinding(
    _CachedRoot,
    namespace="parallax.edit_matrix",
    inheritance=ConcreteSubtype(tag_value="plain"),
):
    memo: ClassVar[object] = object()  # pyright: ignore[reportIncompatibleVariableOverride] - the incompatible override is the behavior under test


def test_the_first_mro_binding_decides_whether_state_is_a_derived_cache() -> None:
    source = _PlainBinding.model_construct(id=1, label="a")
    payload = object()
    attach_instance_state(source, "memo", payload)

    result = source.edit(label="b")

    assert result.memo is payload


def test_entity_and_value_object_changed_edits_keep_distinct_presence_rules() -> None:
    entity = Note.model_construct(id=1, title="alpha")
    value_object = NoteTag.model_construct(label="a")

    edited_entity = entity.edit(title="beta")
    edited_value_object = value_object.edit(label="b")

    assert "tag" in edited_entity.model_fields_set
    assert "body" in edited_entity.model_fields_set
    assert edited_value_object.model_fields_set == {"label"}
