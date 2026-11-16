"""A one-key document (`{computed: ...}`, `{increment: n}`) is no write value of
its own kind (`m-value-object`): at a value object it is the document it is, and
at a scalar member, whatever the verb, its lane's codec refuses it before
anything is buffered."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from parallax.conformance import models
from parallax.core._execution._unit_work.instructions import (
    KeyedWriteInstruction,
    prepare_typed_insert,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.internal.base import UsageError
from tests._support.write_preparation import write_preparation_of

_MODELS = models.load_models()
_PK_SEQUENCE = _MODELS["pk-sequence"]
_CUSTOMER = _MODELS["customer"]

_PREPARERS = (prepare_typed_write, prepare_wire_write)
_LANES = ("typed", "wire")


@pytest.mark.parametrize("prepare", _PREPARERS, ids=_LANES)
def test_a_one_key_value_object_document_is_a_document(prepare: Callable[..., object]) -> None:
    # Judged as the address document it is, which states none of its members.
    insert = KeyedWriteInstruction(
        "insert", "Customer", ({"id": 9, "name": "Ada", "address": {"computed": "maxPlusOne"}},)
    )
    with pytest.raises(
        UsageError,
        match=r"Customer\.address\.street: required attribute is absent \(or null\)$",
    ):
        prepare(insert, write_preparation_of(_CUSTOMER))


# A Typed lane judges a converted value, refused as a write or assignment type
# mismatch; the Wire lane decodes the literal, refused by its codec.
@pytest.mark.parametrize(
    ("prepare", "codes"),
    [
        (
            prepare_typed_write,
            {"write-value-type-mismatch", "write-assignment-value-type-mismatch"},
        ),
        (prepare_wire_write, {"neutral-literal-type-mismatch"}),
    ],
    ids=_LANES,
)
@pytest.mark.parametrize("document", [{"computed": "maxPlusOne"}, {"increment": 1}])
@pytest.mark.parametrize(
    ("mutation", "row"),
    [
        ("insert", {"id": 1, "holder": None}),
        ("amend", {"id": 1, "holder": None}),
        ("replace", {"id": 1, "holder": None}),
        ("insert", {"id": None, "holder": "Ada"}),
        ("delete", {"id": None}),
    ],
    ids=["insert", "amend", "replace", "insert-key", "delete-key"],
)
def test_a_one_key_document_at_a_scalar_member_is_its_codecs_type_mismatch(
    prepare: Callable[..., object],
    codes: set[str],
    document: dict[str, object],
    mutation: str,
    row: dict[str, object],
) -> None:
    stated = {name: document if value is None else value for name, value in row.items()}
    instruction = KeyedWriteInstruction(
        mutation,  # pyright: ignore[reportArgumentType]
        "Badge",
        (stated,),
    )
    with pytest.raises(UsageError, match=r"Badge\.(holder|id): ") as refused:
        prepare(instruction, write_preparation_of(_PK_SEQUENCE))
    assert refused.value.code in codes


def test_only_an_opening_is_prepared_as_one() -> None:
    entity = _PK_SEQUENCE.entities[0]
    with pytest.raises(ValueError, match=r"^'amend' opens no row$"):
        prepare_typed_insert(
            write_preparation_of(_PK_SEQUENCE), "amend", entity, (), valid_from=None, until=None
        )
