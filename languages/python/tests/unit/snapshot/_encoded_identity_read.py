"""A host-checked UUID result cell at the generic result-contract consumer seam.

The Postgres compiler uses native UUID cells. This read's result contract is the
compiled one modified to carry the key encoded, which grades the consumer's
portable encoded-identity contract without claiming that compiler projection.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from parallax.conformance.vo_models import Address
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.db_port import Row
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.read_delivery._page import ROOT_LEVEL, Page, PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._inheritance import ReadResultContract
from parallax.core.temporal_read import Pin
from tests.unit._prepared_read_support import compiled_read


class EncodedIdentity(Entity, table="encoded_identity"):
    id: Attr[UUID] = attr(primary_key=True)
    token: Attr[bytes | None]
    address: Attr[Address | None]


ENCODED_IDENTITIES = DomainModel(EncodedIdentity)
ENCODED_IDENTITY = model_of(ENCODED_IDENTITIES)
KEY_TEXT = "123e4567-e89b-12d3-a456-426614174000"
OTHER_KEY_TEXT = "123e4567-e89b-12d3-a456-426614174001"
KEY = UUID(KEY_TEXT)


def _encoded_identity(contract: ReadResultContract) -> ReadResultContract:
    """``contract`` with its ``id`` cell carried encoded under the wire key ``id_wire``."""
    return replace(
        contract,
        attribute_reads=tuple(
            (
                entity,
                tuple(
                    replace(read, result_key="id_wire", encoded=True)
                    if read.attribute.identity.name == "id"
                    else read
                    for read in reads
                ),
            )
            for entity, reads in contract.attribute_reads
        ),
        result_keys=tuple("id_wire" if key == "id" else key for key in contract.result_keys),
    )


def encoded_identity_read() -> ReadRowConverter:
    """The encoded-identity read, bound; its rows are ``(id_wire, token_hex, address)``."""
    compiled = compiled_read(ENCODED_IDENTITY, "EncodedIdentity")
    return bind(
        CatalogedModel(ENCODED_IDENTITY),
        _encoded_identity(compiled.result_contract),
        compiled.projection,
    )


def encoded_identity_page(*rows: Row) -> Page:
    builder = PageBuilder(ViewSchema.of())
    prepared = encoded_identity_read()
    roots = tuple(prepared.convert_row(row, builder, source=ROOT_LEVEL)[0] for row in rows)
    return builder.finish(roots, Pin())
