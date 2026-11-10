"""The Value Object document a typed insert binds.

A test grading a stored document reads the statement ``tx.insert`` hands the
port, so what it grades is the write path's own output rather than a
composition of that path's steps.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from parallax.core import DomainModel, Entity
from parallax.core.internal.db_port import StructuredDocument
from parallax.snapshot import TxnContext
from tests._support.db_port import ScriptedAdapter, Transact, Write, WriteCall
from tests.unit._transact_support import db_for


def inserted_document(model: DomainModel, entity: Entity) -> Mapping[str, object]:
    """The one Value Object document inserting ``entity`` binds."""
    port = ScriptedAdapter(Transact(Write()))

    def insert(tx: TxnContext) -> None:
        tx.insert(entity)

    db_for(model, port).transact(insert)
    (document,) = (
        bind.document
        for call in port.calls
        if isinstance(call, WriteCall)
        for bind in call.binds
        if isinstance(bind, StructuredDocument)
    )
    return cast("Mapping[str, object]", document)
