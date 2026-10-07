"""The shared sealed-Page fixture and real-read conversion helpers the
materialization suites drive.

A read driver composes a Page by converting provider rows through a bound read
into a Page builder and writing each level's views as that level lands. These
suites need the same composition without a database, so this builds one the same
way — compiling a real read, binding it as a find binds it, and converting rows
through ``ReadRowConverter.convert_row`` — rather than hand-assembling rows or levels
that no driver would produce.

``materialize`` then publishes it through the typed read's own publication, which
is what makes these suites cover the real seam: Root View, allocate, populate, and
per-node state factory, with no stand-in anywhere.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import cast

import pytest

from parallax.core import DomainModel
from parallax.core.base import (
    SQL_NULL,
    DocumentValue,
    NeutralType,
    PresentDocument,
    SqlNull,
    StoredScalarVerdict,
    check_stored_scalar,
)
from parallax.core.deep_fetch import RelationshipViewKey
from parallax.core.deep_fetch._include_tree import build_include_tree
from parallax.core.entity._layout import CatalogedModel, EntityLayout, LayoutCatalog
from parallax.core.entity._model import class_index, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    Metamodel,
    Multiplicity,
    OccurrenceMetadata,
    RelationshipIdentity,
    ValueObjectMetadata,
    entity_by_name,
)
from parallax.core.read_delivery import InvalidData, _convert
from parallax.core.read_delivery._page import (
    ABSENT,
    ROOT_LEVEL,
    ChildSlot,
    Page,
    PageBuilder,
    ViewSchema,
)
from parallax.core.read_delivery._row_converter import ReadRowConverter, bind
from parallax.core.sql_gen._compile import CompiledRead
from parallax.core.temporal_read import Pin
from parallax.core.wire import WireValue, decode_canonical_wire
from parallax.snapshot.handle._read import typed_publication
from tests._support.model_capabilities import graph_construction_for
from tests.unit._prepared_read_support import compiled_read

__all__ = [
    "ConversionCalls",
    "PageFixture",
    "RecordingObserver",
    "documents_of",
    "driver_row",
    "identity_of",
    "invalid_record",
    "layout_of",
    "physical_members",
    "recorded_conversion_dependencies",
    "rendered_members",
    "rendered_occurrence",
]


_NO_PIN = Pin()


def invalid_record(published: object) -> InvalidData[object]:
    """The classified record ``published`` is, narrowed for the assertions on it.

    A published root is typed as widely as the roots it may hold, so narrowing it
    by ``isinstance`` alone leaves the record's own element type unknown under
    pyright strict. Naming the narrowing once keeps every assertion site reading
    as a claim about the record rather than about the type checker.
    """
    assert isinstance(published, InvalidData), published
    return cast("InvalidData[object]", published)


def identity_of(model: Metamodel, name: str) -> EntityIdentity:
    """``name``'s accepted Entity Identity within ``model``."""
    metadata = entity_by_name(model, name)
    assert metadata is not None, name
    return metadata.identity


def documents_of(model: Metamodel, identity: EntityIdentity) -> tuple[ValueObjectMetadata, ...]:
    """The document contributors an instance-form read of ``identity`` projects."""
    position = inheritance_view(model).entity(identity)
    assert position is not None, identity
    return tuple(position.applicable_value_objects)


def layout_of(model: Metamodel, identity: EntityIdentity) -> EntityLayout:
    """``identity``'s member layout under ``model``, for a suite reading converted
    rows without a connection to reach that model's own catalog through."""
    return LayoutCatalog(model).entity(identity)


def driver_row(compiled: CompiledRead, columns: Mapping[str, object]) -> dict[str, object]:
    """``columns`` as a database port hands them over: every document carrier
    ``compiled`` projects arrives as a SQL-null or a present document."""
    carriers = {member.storage.name for member in compiled.projected_documents}
    if compiled.structured_column is not None:
        carriers.add(compiled.structured_column)
    return {key: _carried(value) if key in carriers else value for key, value in columns.items()}


def _carried(value: object) -> object:
    if value is None:
        return SQL_NULL
    if isinstance(value, (SqlNull, PresentDocument)):
        return value
    return PresentDocument(cast("DocumentValue", value))


@dataclass(frozen=True, slots=True)
class ConversionCalls:
    """The stored scalars conversion decoded from canonical wire and admitted,
    in call order."""

    decoded: list[object] = field(default_factory=list[object])
    admitted: list[object] = field(default_factory=list[object])


@contextmanager
def recorded_conversion_dependencies() -> Generator[ConversionCalls]:
    """Record every wire decode and scalar admission conversion reaches, each
    delegating to the original, patched only where the conversion module looks
    them up — document classification's own use of the wire codec is untouched."""
    calls = ConversionCalls()

    def decoding(declared: NeutralType, raw: WireValue) -> object:
        calls.decoded.append(raw)
        return decode_canonical_wire(declared, raw)

    def admitting(
        value: object, declared: NeutralType, *, nullable: bool, temporal_end: bool
    ) -> StoredScalarVerdict:
        calls.admitted.append(value)
        return check_stored_scalar(value, declared, nullable=nullable, temporal_end=temporal_end)

    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(_convert, "decode_canonical_wire", decoding)
        patched.setattr(_convert, "check_stored_scalar", admitting)
        yield calls


class RecordingObserver:
    """A materialization observer recording every cadence event in order."""

    def __init__(self) -> None:
        self.events: list[tuple[str, int]] = []

    def prepared(self, levels: int) -> None:
        self.events.append(("prepared", levels))

    def statement_rendered(self, level: int) -> None:
        self.events.append(("statement_rendered", level))

    def statement_executed(self, level: int, rows: int) -> None:
        del level
        self.events.append(("statement_executed", rows))

    def occurrences_reached(self, count: int) -> None:
        self.events.append(("occurrences_reached", count))

    def witnesses_compared(self, count: int) -> None:
        self.events.append(("witnesses_compared", count))

    def states_decoded(self) -> None:
        self.events.append(("states_decoded", 1))

    def states_shared(self) -> None:
        self.events.append(("states_shared", 1))

    def root_published(self, ordinal: int) -> None:
        self.events.append(("root_published", ordinal))


def rendered_members(layout: EntityLayout, values: tuple[object, ...]) -> dict[str, object]:
    """One member row by declared member name, ``ABSENT`` positions omitted.

    The rendering IS the positional walk every consumer of a row makes, so a name
    absent from it is a position the row holds ``ABSENT`` at — which is what lets
    an assertion state what a read carried without spelling an index.
    """
    rendered: dict[str, object] = {
        attribute.identity.name: values[position]
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    }
    rendered.update(
        {
            occurrence.identity.path[-1]: rendered_occurrence(values[position], occurrence)
            for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
            if values[position] is not ABSENT
        }
    )
    return rendered


def physical_members(layout: EntityLayout, values: tuple[object, ...]) -> dict[str, object]:
    """One member row by each member's physical storage name, ``ABSENT``
    positions omitted and occurrences rendered as :func:`rendered_members` does."""
    rendered: dict[str, object] = {
        attribute.storage.name: values[position]
        for position, attribute in enumerate(layout.attributes)
        if values[position] is not ABSENT
    }
    rendered.update(
        {
            occurrence.storage.name: rendered_occurrence(values[position], occurrence)
            for position, occurrence in enumerate(layout.occurrences, start=layout.attribute_count)
            if values[position] is not ABSENT
        }
    )
    return rendered


def rendered_occurrence(value: object, declared: OccurrenceMetadata) -> object:
    """One occurrence slot by declared member name at every depth: ``None`` for a
    collapsed One, a tuple of mappings for a Many, a mapping otherwise."""
    if declared.multiplicity is Multiplicity.MANY:
        rows = cast("tuple[object, ...]", value) if isinstance(value, tuple) else ()
        return tuple(_occurrence_row(cast("tuple[object, ...]", row), declared) for row in rows)
    return None if value is None else _occurrence_row(cast("tuple[object, ...]", value), declared)


def _occurrence_row(row: tuple[object, ...], declared: OccurrenceMetadata) -> dict[str, object]:
    rendered: dict[str, object] = {
        leaf.identity.name: row[position]
        for position, leaf in enumerate(declared.attributes)
        if row[position] is not ABSENT
    }
    rendered.update(
        {
            nested.identity.path[-1]: rendered_occurrence(row[position], nested)
            for position, nested in enumerate(
                declared.value_objects, start=len(declared.attributes)
            )
            if row[position] is not ABSENT
        }
    )
    return rendered


class PageFixture:
    """One Page under construction, plus the materialization over it.

    ``views`` are the relationship views this Page attaches, declared up front
    because a projection's view row is sized when the row is added and a fan-back
    only names a slot the plan already fixed. A broad view is its relationship's
    own spelling; a narrowed one is that spelling paired with the derived view
    key. They all sit on one unguarded source level, which is the shape
    :meth:`ViewSchema.of` exists for: it lets a suite state a Page with no plan,
    no executor, and no database, at the cost of every projection carrying every
    declared slot rather than only its own level's.

    ``references`` declares back-reference views beside them, each by the target
    Entities its logical claims may resolve to, which is what the plan's slot
    table records for an inverse hop.

    ``model`` overrides the accepted model conversion and Root View judgment without
    changing the classes construction resolves, which is how a suite exercises a
    model and its classes disagreeing — a member the model calls a Value Object
    while the composed class maps it as a scalar. Only a test can reach that
    state: the composition root always takes both facts off one Domain Model.

    Named apart from the production ``PageBuilder`` it drives, so a suite that
    holds both reads which one it is talking to.
    """

    __slots__ = ("_builder", "_cataloged", "_domain", "_model", "_reads", "_sealed")

    def __init__(
        self,
        domain: DomainModel,
        *views: str | tuple[str, str],
        references: Mapping[str, tuple[str, ...]] | None = None,
        model: Metamodel | None = None,
    ) -> None:
        assert class_index(domain) is not None, "the Page suites compose class-backed models"
        self._domain = domain
        self._model = model if model is not None else model_of(domain)
        self._cataloged = CatalogedModel(self._model)
        self._builder = PageBuilder(
            ViewSchema(
                (
                    (
                        *(ChildSlot(self._declared(view)) for view in views),
                        *(
                            ChildSlot(
                                self.view_key(view),
                                targets=frozenset(
                                    identity_of(self._model, target) for target in targets
                                ),
                            )
                            for view, targets in (references or {}).items()
                        ),
                    ),
                )
            )
        )
        self._reads: dict[str, tuple[CompiledRead, ReadRowConverter]] = {}
        self._sealed: tuple[tuple[tuple[int, ...], Pin], Page] | None = None

    def _declared(self, view: str | tuple[str, str]) -> RelationshipViewKey:
        """One declared view: a broad one is a spelling, a narrowed one a pair."""
        if isinstance(view, str):
            return self.view_key(view)
        relationship, narrowed = view
        return self.view_key(relationship, narrowed=narrowed)

    @property
    def builder(self) -> PageBuilder:
        """The production builder this fixture accumulates into."""
        return self._builder

    def node(self, entity: str, columns: Mapping[str, object]) -> int:
        """Convert one driver row of ``entity``, spelled by result key, through
        that Entity's read bound once for this fixture, as a read level would."""
        bound = self._reads.get(entity)
        if bound is None:
            compiled = compiled_read(self._model, entity)
            bound = self._reads[entity] = (compiled, bind(self._cataloged, compiled))
        compiled, prepared = bound
        ref, _resolved, _document, _variant = prepared.convert_row(
            driver_row(compiled, columns), self._builder, source=ROOT_LEVEL
        )
        return ref

    def layout_for(self, entity: str) -> EntityLayout:
        """``entity``'s member layout under this fixture's own accepted model."""
        return self._cataloged.layouts.entity(identity_of(self._model, entity))

    def view_key(self, relationship: str, *, narrowed: str | None = None) -> RelationshipViewKey:
        """One view key, spelled ``Owner.name`` at its declaring position, with
        ``narrowed`` naming the derived view key of a narrowed hop."""
        owner, _, name = relationship.rpartition(".")
        return RelationshipViewKey(
            RelationshipIdentity(identity_of(self._model, owner), name), narrowed
        )

    def attach(
        self,
        parent: int,
        relationship: str,
        value: int | tuple[int, ...] | None,
        *,
        narrowed: str | None = None,
    ) -> None:
        """Write one relationship view onto an already-converted projection."""
        self._builder.write_view(parent, self.view_key(relationship, narrowed=narrowed), value)

    def attach_reference(self, parent: int, relationship: str, family: str, member: str) -> None:
        """Write one declared back-reference onto an already-converted projection:
        the claims its ``member``, spelled ``Owner.name``, names in ``family``."""
        owner, _, name = member.rpartition(".")
        self._builder.write_reference(
            parent,
            self.view_key(relationship),
            identity_of(self._model, family),
            AttributeIdentity(identity_of(self._model, owner), name),
        )

    def page(self, *roots: int, pin: Pin = _NO_PIN) -> Page:
        """The sealed Page with roots in the requested order.

        Sealing invalidates the builder, so a fixture seals once and returns that
        Page thereafter. A suite that needs a second Page builds a second fixture,
        matching the read-executor lifetime.
        """
        asked = (roots, pin)
        if self._sealed is None:
            self._sealed = (asked, self._builder.finish(roots, pin))
        assert self._sealed[0] == asked, "one fixture seals one Page; build a second fixture"
        return self._sealed[1]

    def materialize(
        self, *roots: int, pin: Pin = _NO_PIN
    ) -> tuple[object | InvalidData[object], ...]:
        """Judge, classify, and publish the Page roots through the typed read's
        publication.

        A conforming root is its frozen Entity instance; one some stored state
        contradicted is its :class:`InvalidData` record instead.
        """
        page = self.page(*roots, pin=pin)
        publication = typed_publication(
            self._cataloged, graph_construction_for(self._domain), "fixture"
        )
        queried = self._model.entities[0].identity
        includes = build_include_tree(queried=queried, root=(queried,), positions=())
        return tuple(publication.roots_of(page, includes))
