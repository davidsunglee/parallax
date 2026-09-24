"""The Value Object document a typed insert binds.

A test grading a stored document reads the statement ``tx.insert`` hands the
port, so what it grades is the write path's own output rather than a
composition of that path's steps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core import DomainModel, Entity
from parallax.core.db_port import JsonDocument
from parallax.snapshot.handle import Transaction
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import db_for


def inserted_document(model: DomainModel, entity: Entity) -> Mapping[str, object]:
    """The one Value Object document inserting ``entity`` binds."""
    port = ScriptedAdapter(Transact(Write()))

    def insert(tx: Transaction) -> None:
        tx.insert(entity)

    db_for(model, port).transact(insert)
    (document,) = (
        bind.value
        for call in port.calls
        if isinstance(call, WriteCall)
        for bind in call.binds
        if isinstance(bind, JsonDocument)
    )
    return cast("Mapping[str, object]", document)
