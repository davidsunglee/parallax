from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Final, cast

from parallax.core.internal import read_planning
from parallax.core.internal.entity import Entity, EntityGraphConstruction, IncludePath
from parallax.core.internal.entity._authored_resolver import include_path_node
from parallax.core.internal.entity._expressions import authored_include_path
from parallax.core.internal.metamodel import EntityIdentity
from parallax.core.internal.object_query.validate import validate_include_path
from parallax.core.internal.predicate import root_position
from parallax.core.internal.read_delivery import InvalidData
from parallax.core.internal.wire._facts import WireModelFacts
from parallax.snapshot._inspection import (
    SNAPSHOT_WIRE_AT_CONCRETE_MISMATCH,
    SNAPSHOT_WIRE_AT_UNREQUESTED,
    inspection_refusal,
)
from parallax.snapshot._publication import _wire as wire_materialize
from parallax.snapshot._publication._wire import InstanceReader, WireEntity
from parallax.snapshot._publication._wire_memo import (
    InstanceIdentityMemo,
    WeakIdentityMemo,
    WireMemo,
)
from parallax.snapshot._publication._wire_render import WireRenderer

__all__ = ["TypedWireProjection", "TypedWireSource", "projection_position"]

_EAGER: Final = "Snapshot.wire"
_STREAMED: Final = "SnapshotStream.wire"


@dataclass(frozen=True, slots=True)
class TypedWireSource:
    """What a Typed result retains to project its published values as Wire."""

    construction: EntityGraphConstruction
    wire: WireModelFacts
    includes: read_planning.IncludeTree


class TypedWireProjection:
    """Typed-to-Wire projection of published Typed values under one include shape.

    The constructor fixes the operation refusals name and how long rendered
    outputs are reused. :meth:`for_call` serves one ``Snapshot.wire`` call: one
    renderer, strong identity memo, and encoder for the whole call.
    :meth:`for_delivery` serves one Typed stream: the reader, renderer, and weak
    identity memo last one Page, while the encoder rotates across Pages. The
    reader, renderer, and encoder are allocated on first use, and the owner
    calls :meth:`release` when its scope ends.
    """

    __slots__ = (
        "_construction",
        "_encoder",
        "_includes",
        "_new_memo",
        "_operation",
        "_reader",
        "_renderer",
        "_wire",
    )

    def __init__(
        self,
        construction: EntityGraphConstruction,
        wire: WireModelFacts,
        includes: read_planning.IncludeTree,
        *,
        operation: str,
        new_memo: Callable[[], WireMemo[object]],
    ) -> None:
        self._construction = construction
        self._wire = wire
        self._includes = includes
        self._operation = operation
        self._new_memo = new_memo
        self._reader: InstanceReader | None = None
        self._renderer: WireRenderer[object] | None = None
        self._encoder = None

    @classmethod
    def for_call(cls, source: TypedWireSource) -> TypedWireProjection:
        return cls(
            source.construction,
            source.wire,
            source.includes,
            operation=_EAGER,
            new_memo=InstanceIdentityMemo[object],
        )

    @classmethod
    def for_delivery(
        cls,
        construction: EntityGraphConstruction,
        wire: WireModelFacts,
        includes: read_planning.IncludeTree,
    ) -> TypedWireProjection:
        return cls(
            construction, wire, includes, operation=_STREAMED, new_memo=WeakIdentityMemo[object]
        )

    def project(
        self, value: object, at: IncludePath[Entity, Any] | None
    ) -> WireEntity | InvalidData[WireEntity]:
        """One published node, or its record, at ``at`` or the query root.

        The node is validated before ``at`` resolves, and a data-less record
        passes through once it has. A reader this call creates is retained only
        once every check has passed, so a refusal leaves the projection as it was.
        """
        record = cast("InvalidData[object]", value) if isinstance(value, InvalidData) else None
        node: object | None = record.data if record is not None else cast("object", value)
        reader = self._reader
        concrete: EntityIdentity | None = None
        if node is not None:
            if reader is None:
                reader = InstanceReader(self._construction, operation=self._operation)
            concrete = reader.concrete(node)
        position = projection_position(
            self._includes, self._construction, at, operation=self._operation
        )
        if node is None:
            return cast("InvalidData[WireEntity]", record)
        assert reader is not None and concrete is not None
        return self._rendered(reader, node, record, concrete, position)

    def project_roots(
        self, roots: tuple[object, ...]
    ) -> tuple[WireEntity | InvalidData[WireEntity], ...]:
        """Every root, or its record, at the query root.

        A failure leaves no input, output, or loop reference in this frame,
        which a retained traceback would otherwise keep alive.
        """
        position = self._includes.root
        reader = self._reader
        projected: list[WireEntity | InvalidData[WireEntity]] = []
        value: object | None = None
        record: InvalidData[object] | None = None
        node: object | None = None
        try:
            for index in range(len(roots)):
                value = roots[index]
                record = (
                    cast("InvalidData[object]", value) if isinstance(value, InvalidData) else None
                )
                node = record.data if record is not None else cast("object", value)
                if node is None:
                    projected.append(cast("InvalidData[WireEntity]", record))
                    continue
                if reader is None:
                    reader = InstanceReader(self._construction, operation=self._operation)
                projected.append(
                    self._rendered(reader, node, record, reader.concrete(node), position)
                )
            return tuple(projected)
        finally:
            projected.clear()
            roots = ()
            value = None
            record = None
            node = None

    def begin_page(self, includes: read_planning.IncludeTree) -> None:
        """Drop the previous Page's reader, renderer, and memo, take ``includes``,
        and rotate the encoder."""
        self._clear_page()
        self._includes = includes
        if self._encoder is not None:
            self._encoder.begin_page()

    def release(self) -> None:
        self._clear_page()
        encoder = self._encoder
        self._encoder = None
        if encoder is not None:
            encoder.release()

    def _rendered(
        self,
        reader: InstanceReader,
        node: object,
        record: InvalidData[object] | None,
        concrete: EntityIdentity,
        position: read_planning.PositionId,
    ) -> WireEntity | InvalidData[WireEntity]:
        if not self._includes.admits(position, concrete):
            raise inspection_refusal(
                SNAPSHOT_WIRE_AT_CONCRETE_MISMATCH,
                self._operation,
                f"{concrete.canonical} is not admitted at requested position {position}",
            )
        renderer = self._renderer
        if renderer is None:
            renderer = self._start_rendering(reader)
        rendered = renderer.render_at(node, position)
        return (
            rendered
            if record is None
            else cast("InvalidData[WireEntity]", replace(record, data=rendered))
        )

    def _start_rendering(self, reader: InstanceReader) -> WireRenderer[object]:
        self._reader = reader
        encoder = self._encoder
        if encoder is None:
            encoder = wire_materialize.wire_scalar_cache()
            encoder.begin_page()
            self._encoder = encoder
        renderer = WireRenderer(reader, self._includes, self._wire, encoder, memo=self._new_memo())
        self._renderer = renderer
        return renderer

    def _clear_page(self) -> None:
        renderer = self._renderer
        self._renderer = None
        if renderer is not None:
            renderer.clear()
        reader = self._reader
        self._reader = None
        if reader is not None:
            reader.clear()


def projection_position(
    includes: read_planning.IncludeTree,
    construction: EntityGraphConstruction,
    path: IncludePath[Entity, Any] | None,
    *,
    operation: str,
) -> read_planning.PositionId:
    """The requested position ``path`` names in ``includes``, or its root for
    ``None``, refusing any path that is not an exact requested prefix."""
    if path is None:
        return includes.root
    meta = construction.cataloged.meta
    root = meta.entity(includes.queried)
    if root is None:  # pragma: no cover - the tree came from this exact model
        raise inspection_refusal(
            SNAPSHOT_WIRE_AT_UNREQUESTED,
            operation,
            f"the retained model declares no query root {includes.queried.canonical}",
        )
    try:
        bound = include_path_node(
            authored_include_path(path), includes.queried, meta, construction.classes
        )
        resolved = validate_include_path(bound, meta, root_position(meta, root))
        position = includes.requested_position(resolved)
    except Exception as error:
        raise inspection_refusal(
            SNAPSHOT_WIRE_AT_UNREQUESTED,
            operation,
            f"the requested projection position is not part of this read: {error}",
        ) from error
    if position is None:
        raise inspection_refusal(
            SNAPSHOT_WIRE_AT_UNREQUESTED,
            operation,
            "the requested projection position is not an exact prefix of this read",
        )
    return position
