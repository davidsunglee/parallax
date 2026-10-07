"""A host-checked UUID result cell at the generic compiled-read consumer seam.

The Postgres compiler uses native UUID cells; this double grades the consumer's
portable encoded-identity contract without claiming that compiler projection.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from parallax.conformance.vo_models import Address
from parallax.core import Attr, DomainModel, Entity, attr
from parallax.core.base import UnknownFamilyTag
from parallax.core.db_port import Row
from parallax.core.document_codec import DocumentFinding, MemberShape
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import EntityIdentity, ValueObjectMetadata
from parallax.core.read_delivery._page import ROOT_LEVEL, Page, PageBuilder, ViewSchema
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._compile import AttributeReadContract, CompiledRead
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


@dataclass(frozen=True)
class EncodedIdentityRead:
    compiled: CompiledRead

    @property
    def resolvable(self) -> tuple[EntityIdentity, ...]:
        return self.compiled.resolvable

    @property
    def projected_documents(self) -> tuple[ValueObjectMetadata, ...]:
        return self.compiled.projected_documents

    def row_identity(
        self, row: Row | Mapping[str, object]
    ) -> tuple[EntityIdentity, str | None, UnknownFamilyTag | None, object | None]:
        return self.compiled.row_identity(row)

    def raw_member_classifier(
        self,
        resolved: EntityIdentity,
        key: str,
        *,
        build_object: Callable[[MemberShape, Iterable[object]], object] | None = None,
        build_many: Callable[[Iterable[object]], object] | None = None,
    ) -> Callable[[object], tuple[object, tuple[DocumentFinding, ...]]]:
        return self.compiled.raw_member_classifier(
            resolved, key, build_object=build_object, build_many=build_many
        )

    def raw_member_location(self, resolved: EntityIdentity, key: str) -> str | None:
        return self.compiled.raw_member_location(resolved, key)

    def classified_members(self, resolved: EntityIdentity) -> frozenset[str]:
        return self.compiled.classified_members(resolved)

    def attribute_reads(self, entity: EntityIdentity) -> tuple[AttributeReadContract, ...]:
        return tuple(
            replace(read, result_key="id_wire", encoded=True)
            if read.attribute.identity.name == "id"
            else read
            for read in self.compiled.attribute_reads(entity)
        )

    def raw_member_of(
        self, row: Row | Mapping[str, object], resolved: EntityIdentity, key: str
    ) -> object:
        if key == "id_wire":
            return row[key] if isinstance(row, Mapping) else row[0]
        return self.compiled.raw_member_of(row, resolved, key)

    def raw_member_ordinal(self, resolved: EntityIdentity, key: str) -> int | None:
        return self.compiled.raw_member_ordinal(resolved, "id" if key == "id_wire" else key)

    def publication_keys(self, resolved: EntityIdentity, variant: str | None) -> tuple[str, ...]:
        return tuple(
            "id_wire" if key == "id" else key
            for key in self.compiled.publication_keys(resolved, variant)
        )


def encoded_identity_read() -> ReadRowConverter:
    return bind(
        CatalogedModel(ENCODED_IDENTITY),
        EncodedIdentityRead(compiled_read(ENCODED_IDENTITY, "EncodedIdentity")),
    )


def encoded_identity_page(*rows: Mapping[str, object]) -> Page:
    builder = PageBuilder(ViewSchema.of())
    prepared = encoded_identity_read()
    roots = tuple(prepared.convert_row(row, builder, source=ROOT_LEVEL)[0] for row in rows)
    return builder.finish(roots, Pin())
