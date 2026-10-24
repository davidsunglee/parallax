"""A host-checked UUID result cell at the generic result-contract consumer seam.

The Postgres compiler uses native UUID cells. This read is compiled through a
test-local dialect that renders a UUID Column as its canonical text under
``<column>_wire``, so its SQL and its result contract carry the key encoded
together, which grades the consumer's portable encoded-identity contract
without claiming that compiler rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from uuid import UUID

from parallax.conformance.vo_models import Address
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core import predicate as oa
from parallax.core.base import NeutralType, Uuid
from parallax.core.db_port import Row
from parallax.core.dialect import POSTGRES, Dialect, RenderedScalarCell, ScalarResult
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import entity_by_name
from parallax.core.read_delivery._page import ROOT_LEVEL, Page, PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.temporal_read import Pin
from tests._support.sql import compile_read


class EncodedIdentity(Entity, table="encoded_identity"):
    id: Attr[UUID] = attr(primary_key=True)
    token: Attr[bytes | None]
    address: Attr[Address | None]


ENCODED_IDENTITIES = DomainModel(EncodedIdentity)
ENCODED_IDENTITY = model_of(ENCODED_IDENTITIES)
KEY_TEXT = "123e4567-e89b-12d3-a456-426614174000"
OTHER_KEY_TEXT = "123e4567-e89b-12d3-a456-426614174001"
KEY = UUID(KEY_TEXT)


@dataclass(frozen=True, slots=True)
class _WireUuidDialect(Dialect):
    def render_scalar(
        self,
        alias: str,
        column: str,
        neutral_type: NeutralType,
        *,
        output_alias: str | None = None,
    ) -> RenderedScalarCell:
        if not isinstance(neutral_type, Uuid):
            return Dialect.render_scalar(
                self, alias, column, neutral_type, output_alias=output_alias
            )
        result = ScalarResult(f"{column}_wire", True)
        output = result.publication_key if output_alias is None else output_alias
        expression = f"cast({self.qualified(alias, column)} as text)"
        return RenderedScalarCell(f"{expression} {output}", expression, (), output, result)


_WIRE_UUID = _WireUuidDialect(
    **{field.name: getattr(POSTGRES, field.name) for field in fields(POSTGRES)}
)


def encoded_identity_read() -> ReadRowConverter:
    """The encoded-identity read, bound; its rows are ``(id_wire, token_hex, address)``."""
    entity = entity_by_name(ENCODED_IDENTITY, "EncodedIdentity")
    assert entity is not None
    compiled = compile_read(
        oa.TrueNode(), ENCODED_IDENTITY, _WIRE_UUID, entity, result_form="instance"
    )
    assert compiled.statement.sql.startswith("select cast(t0.id as text) id_wire, ")
    return bind(CatalogedModel(ENCODED_IDENTITY), compiled.result_contract, compiled.projection)


def encoded_identity_page(*rows: Row) -> Page:
    builder = PageBuilder(ViewSchema.of())
    prepared = encoded_identity_read()
    roots = tuple(prepared.convert_row(row, builder, source=ROOT_LEVEL)[0] for row in rows)
    return builder.finish(roots, Pin())
