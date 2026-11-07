"""Turning the physical rows a golden statement returned into the logical result.

The golden SQL projects storage: a raw discriminator column, a shared Structured
Column, a per-branch ``family_variant`` literal, typed ``null`` placeholders. None
of those is a result field. This module derives the result the case authored from
them — ``familyVariant`` from the tag metadata map, a Relational Document Layout's
members from the document it was stored in — and asserts the projection shape each
derivation depends on, reading that shape from the golden text so a zero-row read
still witnesses a dropped column.

Those derivations are ORDERED, and the order is not the caller's to choose: a
document is fanned out at the concrete variant a row names, so the variant must
already be resolved, and each derivation's own absence is invisible until the one
after it runs. So the sequence is offered whole, once per kind of position a row
can stand at — :func:`materialize_read` for the position an Object Query names,
:func:`materialize_hop_level` for one level of a deep fetch — and the steps it is
composed of are private. What comes back is a :class:`PublishedRow`, whose
constructor demands a token this module keeps and which is what the consumers of a
published row accept, so a path assembling the sequence itself fails where it
would have published rather than silently publishing storage. A step that runs
AFTER an entry point projects what it published and demands that provenance on
the way in, so nothing gains it by being projected.

The physical facts themselves are never re-derived here: family topology comes
from :mod:`..inheritance`, column placement from :mod:`..storage_layout`, and the
JSON codec from :mod:`..document_codec`. A table-per-concrete-subtype read's
`union all` is graded by :mod:`.tpcs` before its rows are materialized, since what
that statement must say is a property of the layout rather than of any row.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any, NamedTuple

from ..case import Case, Entity, Model
from ..case_assertions import CaseFailure
from ..document_codec import (
    DocumentEncodingError,
    decode_collection,
    decode_leaf,
    decode_stored,
)
from ..inheritance import (
    STRATEGY_TPCS,
    STRATEGY_TPH,
    Family,
    QueryPosition,
    concrete_target_variant,
    query_position,
    tag_value_to_subtype,
)
from ..storage_layout import (
    AttributeContributor,
    ColumnSlot,
    DocumentMember,
    DocumentPath,
    PositionBranch,
    PositionLayoutView,
    RelationalDocument,
    TableLayout,
    is_scalar_collection,
    position_projection,
    position_view,
)
from . import tpcs
from .execute import (
    golden_projection_columns,
)

# --- unhydratable stored state ----------------------------------------------


class UnavailableLeaf(NamedTuple):
    """A stored leaf that left its result position UNHYDRATABLE (m-snapshot-read).

    A non-null document leaf the declared type does not admit, and a non-nullable
    top-level Entity Attribute that read absent or JSON null, both make the whole
    root unavailable rather than collapsing to a producible value. The judged
    value rides along so a failure names what was stored rather than only where.
    """

    stored: Any


class UnknownFamilyTag(NamedTuple):
    """A stored table-per-hierarchy tag the reading model composes no concrete for.

    It stands where the row's ``familyVariant`` would, so the row keeps its place
    in the result and its correlation columns while claiming no concrete
    identity. The position is unhydratable (`m-read-delivery`), and
    :func:`family_tag_issues` reports it at *family*, the canonical spelling of
    the reader's family root — never at a variant another model composes.
    """

    stored: Any
    family: str


FAMILY_TAG_UNKNOWN = "stored-data-family-tag-unknown"


def is_unavailable(row: Mapping[str, Any]) -> bool:
    """Whether *row*'s stored state left its result position unhydratable."""
    return any(isinstance(value, UnavailableLeaf | UnknownFamilyTag) for value in row.values())


def family_tag_issues(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The unknown-family-tag diagnosis *row* carries, in `then.storedDataIssues`
    vocabulary: a code and the family root, with no member and no object key,
    since the row resolved to no concrete identity."""
    variant = row.get("familyVariant")
    if not isinstance(variant, UnknownFamilyTag):
        return []
    return [{"code": FAMILY_TAG_UNKNOWN, "entity": variant.family}]


# --- materialized rows ------------------------------------------------------


class _MaterializedRow(dict[str, Any]):
    """A result row that still remembers which of its columns are raw VO blobs.

    ``value_object_columns`` are the columns carrying an undecoded Value Object
    occurrence, so an identity-only comparison can drop them.
    """

    __slots__ = ("value_object_columns",)

    def __init__(
        self,
        values: dict[str, Any],
        *,
        value_object_columns: set[str] | None = None,
    ) -> None:
        super().__init__(values)
        self.value_object_columns = value_object_columns or set()


_SEAM = object()
"""The token :class:`PublishedRow`'s constructor demands.

Holding the class is not enough to stamp a row with the provenance its consumers
check for; holding this is, and it is private to this module, so every mint is
written here beside the derivations that provenance stands for. The privacy is
the underscore's — a path that reaches past it forges provenance the way any
Python privacy is forged, and what the token stops is a publishing path written
in the ordinary way.
"""


class PublishedRow(_MaterializedRow):
    """A row that reached its logical result through this module's seam.

    The type is the evidence: a consumer of published rows accepts only this, and
    the constructor demands :data:`_SEAM`, so a path that assembled the
    materialization sequence itself — or skipped it — fails where it would have
    published rather than publishing a raw physical row that still carries a
    discriminator, a branch literal, or an undecoded document. What the row went
    through is checked at the end of the sequence rather than at the type: see
    :func:`_refuse_a_carried_branch`.
    """

    __slots__ = ()

    def __init__(
        self,
        values: dict[str, Any],
        seam: object,
        *,
        value_object_columns: set[str] | None = None,
    ) -> None:
        if seam is not _SEAM:
            raise CaseFailure(
                "a published row is minted with a token this module keeps to itself, "
                "because the provenance stands for the derivation its materialization "
                "entry points run; a row assembled elsewhere has not been through it."
            )
        super().__init__(values, value_object_columns=value_object_columns)


def _materialized_row(row: dict[str, Any]) -> _MaterializedRow:
    """A writable copy of *row* preserving any Value Object bookkeeping it carries."""
    if isinstance(row, _MaterializedRow):
        return _MaterializedRow(dict(row), value_object_columns=set(row.value_object_columns))
    return _MaterializedRow(dict(row))


def _published(row: dict[str, Any]) -> PublishedRow:
    """*row* marked as having come through this module's materialization seam."""
    if isinstance(row, PublishedRow):
        return row
    if isinstance(row, _MaterializedRow):
        return PublishedRow(dict(row), _SEAM, value_object_columns=set(row.value_object_columns))
    return PublishedRow(dict(row), _SEAM)


def edited(row: PublishedRow, assignments: Mapping[str, Any]) -> PublishedRow:
    """Derive a published Wire row by replacing the authored bindings whole."""
    copied = _materialized_row(row)
    copied.update(assignments)
    return _published(copied)


def _refuse_an_unpublished_row(case: Case, step: str, row: Mapping[str, Any]) -> None:
    """Refuse a later projection step's input that never came through the seam.

    A step AFTER the sequence projects what a read published rather than publishing
    anything itself, so its input carries the provenance already. A row that does
    not is one the sequence never ran for: the fan-out that would have replaced its
    stored document with the members it holds, or the derivation that would have
    consumed its branch carrier, may simply not have happened — and projecting it
    would hand that storage on under the provenance of a published row.
    """
    if isinstance(row, PublishedRow):
        return
    raise CaseFailure(
        f"{case.path.name}: {step} projects a row a read PUBLISHED, but this one did "
        f"not come through the materialization seam (materialize_read / "
        f"materialize_hop_level), so it may still carry the "
        f"storage those derivations take out."
    )


def reference_identity_row(row: dict[str, Any]) -> dict[str, Any]:
    """*row* reduced to the identity a ``referenceSql`` oracle can be compared to.

    An undecoded Value Object occurrence is dropped, because the independent
    oracle selects the matched row SET rather than re-deriving the document.
    """
    if not isinstance(row, _MaterializedRow):
        return dict(row)
    return {key: value for key, value in row.items() if key not in row.value_object_columns}


# --- the sequence, per kind of position --------------------------------------


def materialize_read(read: Case, rows: list[dict[str, Any]]) -> list[PublishedRow]:
    """The rows a read of the position its own Object Query names publishes.

    *read* is the ``read`` case whose golden statement returned *rows* — for a
    Scenario step, that step presented as the one read it is. Everything the
    sequence needs it states: the target and any ``narrowTo``, and the golden text
    the projection shape is asserted from. Every read a case states is instance-form
    (`m-sql` *Read projection*), so each carries every applicable Value Object
    occurrence whichever result member asserts it; the flat assertion
    :func:`scalar_columns` leaves them out afterward.

    The order is the sequence's own. The Relational Document Layout fan-out runs
    first, because it is what puts each member back under the result name the
    steps after it read; the Value Object bookkeeping is taken over the fanned-out
    row, so an occurrence that arrived inside the shared document is recorded
    where the identity oracle can drop it again; ``familyVariant`` is derived
    over rows already standing at the columns their own branch spells; and a
    scalar collection in a Column of its own is decoded last, at the concrete
    that variant names.

    Per-variant COLUMN narrowing is deliberately NOT part of this
    (:func:`narrow_to_variant_columns`): a graph node states the per-variant
    shape, while a Scenario step publishes the positional superset, and a caller
    comparing the matched row SET against ``referenceSql`` needs the unnarrowed
    rows either way.
    """
    _refuse_a_case_the_sequence_cannot_read(read)
    materialized = _carrying_value_object_columns(
        read, _materialize_target_tph_document_layout(read, rows)
    )
    target = read.model.entity(read.object_query["target"])
    return [
        _published(_with_direct_collections_decoded(read.model, target, row))
        for row in _materialize_family_variant(read, materialized)
    ]


def materialize_hop_level(
    case: Case,
    entity: Entity,
    rows: list[dict[str, Any]],
    *,
    view_key: str,
    tag_column: str | None,
    variant_map: Mapping[Any, str],
    union: tpcs.LevelUnion | None,
    sole_variant: str | None,
) -> list[PublishedRow]:
    """The rows one level of a deep fetch publishes.

    A hop reaches its position by following an Include Path segment, so like a
    navigated position it carries no Object Query and its own level golden fixes
    the projection shape. What it does carry, and a navigated position does not, is
    a RESOLVED concrete set: *tag_column* is the shared-table discriminator a
    polymorphic table-per-hierarchy hop projects, stated beside the family's
    *variant_map* rather than re-derived here, and *union* is the one statement a
    multi-concrete table-per-concrete-subtype hop reads. A hop naming neither
    targets one concrete or a non-inheritance entity, and *sole_variant* is that
    concrete's spelling, which its statement never projects. A row whose tag the reader
    composes no concrete for keeps its place carrying an :class:`UnknownFamilyTag`
    and is decoded at no variant. The hop states those facts because they are the
    level's own; the derivation over them is this module's, which is why the level
    is materialized here rather than assembled step by step by the caller that
    planned it.

    A *union* level is graded against the layout before its rows are read, as a
    whole read's is, because what its statement must say is a property of the
    position rather than of any row. Each row's branch literal then resolves into
    the ``familyVariant`` it publishes.

    Navigating is instance-form, and a polymorphic level's document fan-out is
    taken per row at the concrete that row's own derived ``familyVariant`` names.
    """
    if union is not None:
        at_their_variant = _rows_at_their_union_branch(case, union, rows, view_key=view_key)
    elif tag_column is None:
        return [
            _published(_with_direct_collections_decoded(case.model, entity, row))
            for row in _carrying_variant(
                sole_variant, _materialize_document_layout(case, entity, rows)
            )
        ]
    else:
        family_root = _family_root(case, entity.canonical_name)
        at_their_variant = [
            _materialize_hop_variant(
                case,
                row,
                view_key=view_key,
                tag_column=tag_column,
                variant_map=variant_map,
                family_root=family_root,
            )
            for row in rows
        ]
    return [
        _published(row)
        if isinstance(row["familyVariant"], UnknownFamilyTag)
        else _published(
            _with_direct_collections_decoded(
                case.model,
                entity,
                _materialize_document_layout(case, case.model.entity(row["familyVariant"]), [row])[
                    0
                ],
            )
        )
        for row in at_their_variant
    ]


def _refuse_a_case_the_sequence_cannot_read(read: Case) -> None:
    """Refuse a case of another shape: it carries a different action member and
    would answer ``target`` and ``statements`` from somewhere else."""
    if read.shape != "read":
        raise CaseFailure(
            f"{read.path.name}: rows are materialized against the READ they belong to, "
            f"but this case's shape is {read.shape!r}. A Scenario step, a write, or any "
            f"other shape is presented as the one read it states before its rows are "
            f"materialized (m-case-format)."
        )


def _carrying_value_object_columns(read: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*rows* remembering which of their columns are still raw Value Object blobs."""
    target = read.object_query.get("target")
    if not isinstance(target, str):
        return rows
    columns = _position_value_object_columns(read, read.model.entity(target))
    return [_MaterializedRow(row, value_object_columns=columns & row.keys()) for row in rows]


def _position_value_object_columns(case: Case, entity: Entity) -> set[str]:
    """Every top-level Value Object Column a read of *entity*'s position can carry.

    An abstract inheritance node declares none of its concretes' own members, so
    an occurrence a single concrete declares is invisible from the position the
    query targeted while still arriving in that concrete's own rows. The union
    over the position is therefore what an instance-form read of it materializes,
    and it collapses to the entity's own occurrences for every concrete or
    non-inheritance target.
    """
    family = Family(case.model.entity_defs)
    position = family.concrete_descendants(entity.canonical_name) if entity.role else []
    return {
        occurrence["column"]
        for name in (entity.canonical_name, *position)
        for occurrence in case.model.entity(name).value_objects
    }


def read_effective_set(case: Case, family: Family, target_name: str) -> list[str]:
    """The effective concrete-subtype set an abstract-target read resolves over.

    The queried position is *target_name*, further constrained by the query's own
    ``narrowTo`` clause — then the narrowed selection drives the projection
    superset. A ``narrow`` inside the predicate (grouped branch predicates) leaves
    the target's full family in scope, as does an Include Path's own source guard,
    which qualifies a path's source objects rather than the read's result.
    """
    narrow_to = case.object_query.get("narrowTo")
    if isinstance(narrow_to, list):
        return family.resolve_to_set(narrow_to)
    return family.effective_concrete_set(target_name)


def _document_value(document: Any, path: tuple[str, ...]) -> Any:
    """The raw stored value at *path*, or ``None`` where the walk stops."""
    current = document
    for name in path:
        if not isinstance(current, dict) or name not in current:
            return None
        current = current[name]
    return current


def _materialize_document_layout(
    case: Case, entity: Entity, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fan a Relational Document Layout read's Structured Column out into its members,
    under the result names a ``Columns`` layout would have used.

    The same shape as :func:`_materialize_family_variant`: the golden SQL projects a
    raw column and the logical result is derived from it here, because the Structured
    Column is never itself a result field (`m-sql`).

    ``entity`` owns ``rows``, which is the level of a deep fetch they came from
    rather than always the case's read target: every level projects its own
    Structured Column and decodes its own members out of it.

    Each leaf decodes by its DECLARED type (:func:`decode_leaf`), not by the JSON
    value's own shape, and an absent key and an explicit JSON null both read as one
    absence — the single not-present state a NULL Column has.

    An owner with a Structured Column and no member inside it fans out nothing and
    still drops the column: an observation-bearing read projects it for the stored
    document itself (`m-sql` *Read projection*, rule 5), which is provenance rather
    than a result field.
    """
    document = case.model.storage_layout.document(entity.canonical_name)
    column, members = document.column, document.members
    if not column:
        return rows
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if column not in row:
            return rows
        document = decode_stored(row[column])
        node = {key: value for key, value in row.items() if key != column}
        for member in members:
            stored = _document_value(document, member.path)
            node[member.column] = (
                stored if member.type_spelling is None else _decoded_leaf(entity, member, stored)
            )
        materialized.append(node)
    return materialized


def _decoded_leaf(entity: Entity, member: DocumentMember, stored: Any) -> Any:
    """One document-resident leaf as the read publishes it, or the judgement that
    left its root unhydratable.

    Two stored states are unhydratable and the rest are ordinary values: a
    non-null leaf the declared type does not admit, and — for a top-level Entity
    Attribute alone — an absent or JSON-null one the model declares non-nullable.
    The second is `m-snapshot-read`'s layout-parity rule: a document member and a
    SQL `NULL` Column are one logical state, so the document arm may not publish
    a hydratable absence where the Column arm publishes none.
    """
    try:
        if member.many:
            return decode_collection(member.type_spelling or "", stored)
        if stored is None:
            return None if _leaf_nullable(entity, member) else UnavailableLeaf(None)
        return decode_leaf(member.type_spelling or "", stored)
    except DocumentEncodingError:
        return UnavailableLeaf(stored)


def _with_direct_collections_decoded(
    model: Model, entity: Entity, row: dict[str, Any]
) -> dict[str, Any]:
    """*row* with each scalar collection stored in a Column of its own decoded to
    the elements a read publishes, or to the judgement leaving its root unhydratable.

    A collection the Relational Document Layout fan-out already read out of the
    shared document is left alone, so every published row — golden or
    ``referenceSql`` — carries one logical value per collection
    whichever Column stored it, exactly as :func:`_decoded_leaf` does for the
    document arm.
    """
    concrete = variant_entity(model, entity, row)
    resident = {
        member.column for member in model.storage_layout.document(concrete.canonical_name).members
    }
    columns = [
        attribute
        for attribute in concrete.attributes
        if is_scalar_collection(attribute)
        and attribute["column"] in row
        and attribute["column"] not in resident
    ]
    if not columns:
        return row
    decoded = _materialized_row(row)
    for attribute in columns:
        stored = decode_stored(row[attribute["column"]])
        try:
            decoded[attribute["column"]] = decode_collection(attribute["type"], stored)
        except DocumentEncodingError:
            decoded[attribute["column"]] = UnavailableLeaf(stored)
    return decoded


def _leaf_nullable(entity: Entity, member: DocumentMember) -> bool:
    """Whether the top-level Attribute *member* spells may hold no value."""
    declared = next(
        (
            attribute
            for attribute in entity.attributes
            if attribute["name"] == member.address.path[0]
        ),
        None,
    )
    return declared is None or bool(declared.get("nullable"))


def _materialize_target_document_layout(
    case: Case, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """:func:`_materialize_document_layout` over the case's own read target.

    A top-level read's rows belong to its query's own ``target``; a deep fetch's
    child level does not, which is why the entity is an argument there and resolved
    here.
    """
    target_name = case.object_query.get("target")
    if not isinstance(target_name, str):
        return rows
    return _materialize_document_layout(case, case.model.entity(target_name), rows)


def _materialize_target_tph_document_layout(
    case: Case, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Decode an abstract TPH document only after its raw tag resolves the variant."""
    position = query_position(case.object_query, case.model.entity_defs)
    if position is None or position.strategy != STRATEGY_TPH:
        return _materialize_target_document_layout(case, rows)
    target = case.model.entity(position.target)
    if not case.model.storage_layout.document(target.canonical_name).column:
        return _materialize_target_document_layout(case, rows)

    tagged = _materialize_family_variant(case, rows)
    materialized: list[dict[str, Any]] = []
    for row in tagged:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            materialized.append(row)
            continue
        (decoded,) = _materialize_document_layout(case, case.model.entity(variant), [row])
        materialized.append(decoded)
    return materialized


# --- familyVariant ----------------------------------------------------------


def _materialize_family_variant(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize ``familyVariant`` for any read of an inheritance participant.

    A non-inheritance read returns *rows* unchanged, and a concrete-target read
    takes the spelling its target names, since its statement projects no carrier.
    For an abstract target the golden SQL projects the raw tag column and
    the full concrete superset; this asserts that projection shape, then replaces the
    tag column with the derived ``familyVariant`` (``tagValue`` -> concrete subtype
    name) so the materialized rows can be compared to ``then.rows``.

    Everything it classifies, narrows, and grades against comes from *case*: the
    target and its ``narrowTo``, the Sort Keys and cap a `union all` wrap renders,
    and the golden statement whose projection shape is asserted. A Scenario step
    states all four under the step, so it is materialized against the step
    presented as the read it is, never against the Scenario case around it.
    """
    position = query_position(case.object_query, case.model.entity_defs)
    if position is None:
        return _carrying_variant(
            concrete_target_variant(case.object_query, case.model.entity_defs), rows
        )
    family, target_name = position.family, position.target
    if position.strategy == STRATEGY_TPCS:
        return _materialize_tpcs_family_variant(case, rows, family, target_name)
    if position.strategy != STRATEGY_TPH:
        return rows

    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    effective = read_effective_set(case, family, target_name)
    expected_columns = set(position_projection(case.model.storage_layout, family, effective))

    # Projection-shape assertion, derived from the GOLDEN SQL projection rather than a
    # sample row, so it is row-count-INDEPENDENT: a zero-row abstract read still
    # witnesses a golden that drops the raw tag column or a concrete-superset column
    # (an empty result set carries no keys to inspect, but the golden text always does).
    # The tag column is checked first so a tag-only omission reports the specific tag
    # diagnostic (the superset set below also contains the tag).
    projected = golden_projection_columns(case)
    if tag_column not in projected:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read does not project the tag "
            f"column {tag_column!r}; an abstract read MUST project the raw tag column "
            f"so familyVariant can be materialized (m-sql / m-inheritance, resolved Q6)."
        )
    missing = expected_columns - projected
    if missing:
        raise CaseFailure(
            f"{case.path.name}: abstract-target read projection is missing "
            f"concrete-superset column(s) {sorted(missing)}; an abstract read MUST "
            f"project the full concrete superset PLUS the raw tag column "
            f"(m-sql / m-inheritance, resolved Q6)."
        )

    return _materialize_tph_family_variant(case, family, target_name, rows)


def _carrying_variant(variant: str | None, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """*rows* of one known concrete, each carrying its *variant* spelling."""
    if variant is None:
        return rows
    return [_tagged(_materialized_row(row), variant) for row in rows]


def _tagged(row: _MaterializedRow, variant: str | UnknownFamilyTag) -> _MaterializedRow:
    row["familyVariant"] = variant
    return row


def _materialize_tph_family_variant(
    case: Case, family: Family, target_name: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace each row's raw tag column with the derived ``familyVariant``."""
    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    variant_map = tag_value_to_subtype(case.model.entity_defs)
    family_root = _family_root(case, target_name)
    return [
        _with_family_variant(
            case,
            _materialized_row(row),
            tag_column=tag_column,
            variant_map=variant_map,
            family_root=family_root,
            subject="abstract-target read",
        )
        for row in rows
    ]


def _family_root(case: Case, name: str) -> str:
    """The canonical spelling of the reader's family root above *name*."""
    return Family(case.model.entity_defs).root_of(name) or case.model.entity(name).canonical_name


def _with_family_variant(
    case: Case,
    row: _MaterializedRow,
    *,
    tag_column: str,
    variant_map: Mapping[Any, str],
    family_root: str,
    subject: str,
) -> _MaterializedRow:
    """*row* with its raw tag column replaced by the ``familyVariant`` the tag names.

    The one tag-to-variant transformation, applied wherever a row arrives carrying a
    table-per-hierarchy discriminator. *row* is transformed IN PLACE, so a caller hands
    over a private copy. *subject* names the read in the diagnostic, since a whole-read
    tag failure and a deep-fetch hop's are the same defect reported against different
    reads.

    A tag the reader's composed family names no concrete subtype for is stored
    data the read classifies rather than a defect of the case: the row carries an
    :class:`UnknownFamilyTag` at *family_root* in place of its variant
    (`m-inheritance` *Partially composed families*). A missing tag column is a
    projection defect and still fails the case.
    """
    if tag_column not in row:
        raise CaseFailure(
            f"{case.path.name}: {subject} does not project the tag column "
            f"{tag_column!r}; familyVariant cannot be materialized (m-inheritance)."
        )
    tag_value = row.pop(tag_column)
    variant = variant_map.get(tag_value)
    return _tagged(row, UnknownFamilyTag(tag_value, family_root) if variant is None else variant)


def _materialize_hop_variant(
    case: Case,
    row: dict[str, Any],
    *,
    view_key: str,
    tag_column: str,
    variant_map: Mapping[Any, str],
    family_root: str,
) -> dict[str, Any]:
    """Replace a polymorphic deep-fetch child row's raw tag column with ``familyVariant``.

    The table-per-hierarchy analogue of :func:`_materialize_family_variant` for a
    deep-fetch hop, whose own step golden fixes the projection shape a whole read has
    to assert first. The hop states its own facts — its attach key, its tag column, and
    the family's tag map — rather than handing over the fetch step it belongs to,
    because the hop is the caller's vocabulary and the derivation is this module's.
    """
    return _with_family_variant(
        case,
        _materialized_row(row),
        tag_column=tag_column,
        variant_map=variant_map,
        family_root=family_root,
        subject=f"polymorphic hop {view_key}",
    )


def _rows_at_their_union_branch(
    case: Case, union: tpcs.LevelUnion, rows: list[dict[str, Any]], *, view_key: str
) -> list[dict[str, Any]]:
    """Grade a multi-concrete deep-fetch level's `union all`, then restore its rows.

    The table-per-concrete-subtype analogue of :func:`_materialize_hop_variant`. A
    level's rows align to the position's whole superset, as every read's do.
    """
    family = Family(case.model.entity_defs)
    position = _tpcs_position(case, family, union.concretes)
    tpcs.assert_level_union_shape(case, position.view, position.branch_variants, union)
    return [
        _tpcs_row_at_its_branch(case, position, row, subject=f"polymorphic hop {view_key}")
        for row in rows
    ]


def level_order_binds(
    case: Case, concretes: list[str], order_by: Sequence[dict[str, Any]], dialect: str
) -> tuple[str, ...]:
    """What a level over *concretes* ordered by *order_by* binds after every branch."""
    family = Family(case.model.entity_defs)
    position = _tpcs_position(case, family, concretes)
    return tpcs.level_order_binds(case, position.view, position.branch_variants, order_by, dialect)


def narrow_to_variant_columns(case: Case, row: PublishedRow) -> PublishedRow:
    """Narrow *row* to its own concrete variant's declared columns (m-case-format
    "Read targeting", the per-variant node shape).

    A materialized instance carries only its own branch's members — its inherited
    chain plus its own declared attributes — never a sibling branch's null-padded
    column: a `Dog` node has no `indoor` key to be null. A `then.rows` assertion
    keeps the full concrete-superset row instead (:func:`scalar_columns`); this
    ADDITIONAL narrowing applies only where a row already carries a
    materialized ``familyVariant`` (a no-op for a non-inheritance entity, whose
    rows state none, and for a concrete-target read, whose rows hold only their
    own branch's columns).

    Narrowing projects what a read published rather than publishing anything, so
    a row arrives with that provenance and leaves carrying it forward.
    """
    _refuse_an_unpublished_row(case, "per-variant column narrowing", row)
    variant = row.get("familyVariant")
    if not isinstance(variant, str):
        return row
    family = Family(case.model.entity_defs)
    own_columns = set(position_projection(case.model.storage_layout, family, [variant]))
    own_columns.update(
        member.column
        for member in case.model.storage_layout.document(
            case.model.entity(variant).canonical_name
        ).members
    )
    return PublishedRow(
        {key: value for key, value in row.items() if key == "familyVariant" or key in own_columns},
        _SEAM,
        value_object_columns=set(row.value_object_columns),
    )


def scalar_columns(case: Case, rows: list[PublishedRow]) -> list[PublishedRow]:
    """*rows* as the scalar-column view a `then.rows` assertion states.

    The read published every member; the assertion observes its scalars across the
    position's superset (`m-case-format` *Read result form*). So a Value Object
    contributor leaves the row, a sibling's scalar the row's own branch does not hold
    is padded ``null`` — a document-resident one, or one whose repeated spelling only
    its own branch restored (:func:`_tpcs_row_at_its_branch`) — exactly as any other
    Column is, and nothing else moves: a scalar collection, a document-resident
    scalar, and any unexpected scalar column stay for the comparison to judge,
    including a scalar reusing the Column a sibling's Value Object occupies. A scalar
    the row's own concrete declares is never padded, so a read that lost it still
    fails the comparison.

    Like :func:`narrow_to_variant_columns` this projects what a read published, so
    each row arrives with that provenance and leaves carrying it forward.
    """
    target = case.model.entity(case.object_query["target"])
    position = query_position(case.object_query, case.model.entity_defs)
    concretes = (
        [target]
        if position is None
        else [
            case.model.entity(name)
            for name in read_effective_set(case, position.family, position.target)
        ]
    )
    value_objects = {
        occurrence["column"] for entity in concretes for occurrence in entity.value_objects
    }
    padding = (
        []
        if position is None
        else [
            *(
                member.column
                for entity in concretes
                for member in case.model.storage_layout.document(entity.canonical_name).members
                if member.type_spelling is not None
            ),
            *_repeated_scalar_spellings(case, position),
        ]
    )
    scalars: list[PublishedRow] = []
    for row in rows:
        _refuse_an_unpublished_row(case, "the scalar-column assertion", row)
        own = {
            attribute["column"] for attribute in variant_entity(case.model, target, row).attributes
        }
        scalars.append(
            _published(
                dict.fromkeys(column for column in padding if column not in own)
                | {
                    key: value
                    for key, value in row.items()
                    if key not in value_objects or key in own
                }
            )
        )
    return scalars


def _repeated_scalar_spellings(case: Case, position: QueryPosition) -> list[str]:
    """The scalar spellings a table-per-concrete-subtype *position* projects more than once.

    Only these leave a row short of the superset: every other Column reaches each
    branch under its own spelling, so its absence from a row stays a defect for the
    comparison to find rather than something to pad.
    """
    if position.strategy != STRATEGY_TPCS:
        return []
    effective = read_effective_set(case, position.family, position.target)
    union = _tpcs_position(case, position.family, effective)
    return [
        spelling
        for column, spelling in zip(union.view.columns, union.superset, strict=True)
        if isinstance(column.contributor, AttributeContributor)
        and union.column_counts[spelling] > 1
    ]


# --- Value Object occurrences -----------------------------------------------


def _project_value_object(occurrence: dict[str, Any], decoded: Any) -> Any:
    """Project a decoded document slot to its DECLARED value-object shape.

    The projection answers one occurrence's own value once its parent has decided
    the position exists at all (:func:`_project_members`):

    * a ``one`` member is a nested object when the slot is a JSON object, else
      ``None`` — a SQL-NULL column, a JSON ``null``, and a non-object intermediate
      all collapse the composite (m-document-codec);
    * a ``many`` member is the collection of its element projections when the
      slot is a JSON array of objects, else ``[]``, because a ``many`` has no
      absent state: an omitted key, a JSON ``null``, and ``[]`` are three stored
      spellings of one zero value. A non-array, and an array holding any
      non-object element, are one wrong-kind ``many`` AT THE OCCURRENCE
      POSITION — the whole collection collapses and no element is projected, so
      a conforming sibling element never survives a malformed one
      (m-document-codec).

    Element order within a ``many`` member is semantic (m-value-object), so this
    projection preserves JSON document order and metadata-aware graph comparison
    checks those elements positionally.
    """
    if occurrence.get("multiplicity", "one") == "many":
        if isinstance(decoded, list) and all(isinstance(element, dict) for element in decoded):
            return [_project_members(occurrence, element) for element in decoded]
        return []
    if isinstance(decoded, dict):
        return _project_members(occurrence, decoded)
    return None


def _project_members(occurrence: dict[str, Any], obj: Any) -> dict[str, Any]:
    """Build the declared-member projection of one value-object document object.

    Undeclared keys are omitted and each declared member the document HOLDS is
    decoded by its declared type (:func:`decode_leaf`) rather than copied out,
    because the document stores the codec's portable spelling. Which declared
    members become keys is not decided here: this projection realizes the read
    contract (m-snapshot-read "What a materialized value carries") and is graded
    against a language implementation of the same contract, so each position where a
    key survives a document that did not hold it is read from there rather than
    restated (:func:`_publishes_when_omitted`). The one position that runs the other
    way has no case here, because :func:`decode_leaf` raises on an undecodable leaf
    instead of classifying it. What the projection adds of its own is the decoding
    alone, which is why a stored state a hydration rule collapses projects that
    collapse whole rather than element by element.
    """
    source = obj if isinstance(obj, dict) else {}
    node: dict[str, Any] = {}
    for attribute in occurrence.get("attributes", []):
        if is_scalar_collection(attribute):
            node[attribute["name"]] = decode_collection(
                attribute["type"], source.get(attribute["name"])
            )
        elif attribute["name"] in source:
            node[attribute["name"]] = decode_leaf(attribute["type"], source[attribute["name"]])
    for nested in occurrence.get("valueObjects", []):
        if _publishes_when_omitted(nested) or nested["name"] in source:
            node[nested["name"]] = _project_value_object(nested, source.get(nested["name"]))
    return node


def _publishes_when_omitted(nested: dict[str, Any]) -> bool:
    return nested.get("multiplicity", "one") == "many" or not nested.get("nullable", False)


def _materialize_owner_node(entity: Entity, row: dict[str, Any]) -> dict[str, Any]:
    """A read row with its top-level value-object columns decoded + projected.

    Scalar columns pass through under their result-column name; each declared
    top-level value object's document column is decoded and replaced by its
    declared projection, keyed by the value-object name. A value-object column
    the golden SELECT did not project is left untouched (no synthetic null).
    """
    node = dict(row)
    for occurrence in entity.value_objects:
        column = occurrence["column"]
        if column not in node:
            continue
        node[occurrence["name"]] = _project_value_object(
            occurrence, decode_stored(node.pop(column))
        )
    return node


def at_value_object_columns(model: Model, entity: Entity, row: PublishedRow) -> dict[str, Any]:
    """*row*, read at *entity*'s position, as a step's ``expectRows`` entry states it.

    A decoded top-level Value Object stands under its occurrence name for the graph
    a step can assemble, while a flat row keeps the projection's physical spelling
    (`m-case-format` *Read result form*).
    """
    columns = {
        occurrence["name"]: occurrence["column"]
        for occurrence in variant_entity(model, entity, row).value_objects
    }
    return {columns.get(key, key): value for key, value in row.items()}


def variant_entity(model: Model, entity: Entity, row: Mapping[str, Any]) -> Entity:
    """The concrete Entity *row* names through its own materialized ``familyVariant``.

    *entity* is the position a read TARGETED, which for an abstract-target read
    declares none of its concretes' own members. A row carrying no variant — a
    non-inheritance entity — stands at its position.
    """
    variant = row.get("familyVariant")
    return model.entity(variant) if isinstance(variant, str) else entity


def materialize_variant_owner_node(case: Case, entity: Entity, row: PublishedRow) -> PublishedRow:
    """:func:`_materialize_owner_node` against the concrete Entity *row* names itself.

    A Value Object occurrence is decoded and projected against the Entity that
    DECLARES it, and an abstract inheritance position declares none of them:
    decoding a `Memo` at the abstract `Document` it was queried through would leave
    the stored document standing as the raw carrier it is, so an unknown key
    written by another version of the application would reach the logical result
    (`m-document-codec`).

    The decode PROJECTS a row an entry point above already published rather than
    publishing one of its own, so it demands that provenance and carries it
    forward. It is also the last step of the sequence, so it is where a row that
    skipped an earlier one is still recognizable: it refuses a row standing at a
    polymorphic position that still carries the branch carrier ``familyVariant`` is
    derived from.
    """
    _refuse_an_unpublished_row(case, "the owner-node decode", row)
    _refuse_a_carried_branch(case, entity, row)
    return _published(_materialize_owner_node(variant_entity(case.model, entity, row), row))


def _refuse_a_carried_branch(case: Case, entity: Entity, row: Mapping[str, Any]) -> None:
    """Refuse a row still carrying the branch carrier its position resolves through.

    A position over two or more concretes names each row's variant physically — a
    table-per-hierarchy tag column, a table-per-concrete-subtype branch literal —
    and the derivation that reads one CONSUMES it, replacing it with
    ``familyVariant``. So a row carrying a carrier and no ``familyVariant``
    reached publication without that derivation having run.

    Both halves of that test are load-bearing, because a carrier spelling is not
    reserved: a concrete's own Attribute may claim the Column a branch literal is
    projected under, in which case the read renames the collision away and the
    published row carries that Column legitimately. Carrying the derived variant
    beside it is what tells the two apart.

    Stated one-directionally: presence is refused, absence never demanded. A row
    that stands somewhere else carries no carrier at all — the levels a multi-hop
    load walked through, a concrete-target read that already names its one
    variant — and this must not turn either into a failure.
    """
    if "familyVariant" in row:
        return
    position = query_position({"target": entity.canonical_name}, case.model.entity_defs)
    if position is None:
        return
    family, target = position.family, position.target
    if len(family.effective_concrete_set(target)) < 2:
        return
    if position.strategy == STRATEGY_TPH:
        carrier = family.tag_column_of(target)
    elif position.strategy == STRATEGY_TPCS:
        carrier = tpcs.VARIANT_COLUMN
    else:
        carrier = None
    if carrier is None or carrier not in row:
        return
    raise CaseFailure(
        f"{case.path.name}: a row published at the polymorphic position {target} still "
        f"carries its branch carrier {carrier!r} and no derived `familyVariant`. That "
        f"column names the row's concrete variant physically and is never a result "
        f"member, so the derivation that reads it consumes it (m-inheritance / m-sql)."
    )


class _TpcsPosition(NamedTuple):
    """What restoring one `union all` row to its own branch takes.

    ``view`` and ``branch_variants`` are the position's own layout facts, which
    :mod:`.tpcs` also grades the golden against; the rest is the aligned projection
    those facts derive — the physical spelling each ordinal carries, the
    collision-safe alias it is projected under, how many ordinals share that
    spelling, and per variant the slot-or-absence entry and Table layout its branch
    reads.
    """

    view: PositionLayoutView
    branch_variants: list[tuple[PositionBranch, str]]
    superset: list[str]
    result_aliases: list[str]
    column_counts: dict[str, int]
    slots_by_variant: dict[str, tuple[ColumnSlot | None, ...]]
    layouts_by_variant: dict[str, TableLayout]


def _tpcs_position(case: Case, family: Family, effective: list[str]) -> _TpcsPosition:
    """The table-per-concrete-subtype position *effective* selects, as its rows read it."""
    ordered = family.canonical_concrete_order(effective)
    view = position_view(case.model.storage_layout, family, effective)
    if view is None:
        raise CaseFailure(
            f"{case.path.name}: the storage layout resolves no position for the effective "
            f"concrete set {ordered}; a table-per-concrete-subtype abstract read must map "
            f"onto one family's canonical concrete selection."
        )
    branch_variants = tpcs.branch_variants(case, family, ordered, view)
    superset = list(view.column_spellings)
    return _TpcsPosition(
        view=view,
        branch_variants=branch_variants,
        superset=superset,
        result_aliases=tpcs.result_aliases(superset),
        column_counts={column: superset.count(column) for column in set(superset)},
        slots_by_variant={name: branch.slots for branch, name in branch_variants},
        layouts_by_variant={name: branch.layout for branch, name in branch_variants},
    )


def _tpcs_row_at_its_branch(
    case: Case, position: _TpcsPosition, row: dict[str, Any], *, subject: str
) -> dict[str, Any]:
    """*row* restored to the `union all` branch its ``family_variant`` literal names.

    The literal becomes ``familyVariant``; a column observed through a collision-safe
    internal alias is restored to the physical spelling its OWN branch's slot carries,
    an alias standing for a slot that branch does not own is dropped, and the branch's
    own Structured Column decodes through that branch's placements. The TPCS
    counterpart of the table-per-hierarchy tag-to-variant materialization
    (:func:`_with_family_variant`), which likewise names its *subject* so the same
    defect reads alike whether reported against a whole read, a navigated position, or
    a deep-fetch level.
    """
    new_row = _materialized_row(row)
    if tpcs.VARIANT_COLUMN not in new_row:
        raise CaseFailure(
            f"{case.path.name}: {subject} does not project the "
            f"{tpcs.VARIANT_COLUMN!r} literal; familyVariant cannot be "
            f"materialized (m-sql)."
        )
    variant = new_row.pop(tpcs.VARIANT_COLUMN)
    slots = position.slots_by_variant.get(variant)
    if slots is None:
        raise CaseFailure(
            f"{case.path.name}: {tpcs.VARIANT_COLUMN!r} literal {variant!r} names no "
            f"branch of the effective concrete set {sorted(position.slots_by_variant)}."
        )
    for slot, column, result_alias in zip(
        slots, position.superset, position.result_aliases, strict=True
    ):
        if (
            result_alias in new_row
            and result_alias != column
            and (position.column_counts[column] == 1 or slot is not None)
        ):
            new_row[column] = new_row.pop(result_alias)
        elif position.column_counts[column] > 1 and slot is None:
            new_row.pop(result_alias, None)
    return _materialize_tpcs_document_row(
        case, position.layouts_by_variant[variant], _tagged(new_row, variant)
    )


def _materialize_tpcs_family_variant(
    case: Case, rows: list[dict[str, Any]], family: Family, target_name: str
) -> list[dict[str, Any]]:
    """Rename the projected `familyVariant` literal column for a TPCS abstract read.

    Asserts the `union all` branch/projection shape, then restores each row to its own
    branch (:func:`_tpcs_row_at_its_branch`) so the materialized rows compare against
    ``then.rows`` — the TPCS counterpart of the TPH tag-to-variant materialization
    (m-inheritance / m-sql).
    """
    position = _tpcs_position(case, family, read_effective_set(case, family, target_name))
    tpcs.assert_union_shape(case, position.view, position.branch_variants)
    return [
        _tpcs_row_at_its_branch(
            case, position, row, subject="table-per-concrete-subtype abstract read"
        )
        for row in rows
    ]


def _materialize_tpcs_document_row(
    case: Case, layout: TableLayout, row: dict[str, Any]
) -> dict[str, Any]:
    """Decode one concrete TPCS branch through that branch's placements."""
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None or slot.column not in row:
        return row
    document = decode_stored(row[slot.column])
    materialized = {key: value for key, value in row.items() if key != slot.column}
    entities = {entity.canonical_name: entity for entity in case.model.entities}
    for candidate in case.model.storage_layout.tables:
        if candidate.contribution(slot.contributor) is None:
            continue
        for declaration, name, _placement in _top_level_document_members(candidate, entities):
            attribute = next(
                (item for item in declaration.attributes if item["name"] == name), None
            )
            if attribute is not None:
                materialized.setdefault(attribute["column"], None)
    for entity, name, placement in _top_level_document_members(layout, entities):
        attribute = next((item for item in entity.attributes if item["name"] == name), None)
        occurrence = next((item for item in entity.value_objects if item["name"] == name), None)
        stored = _document_value(document, placement.path)
        if attribute is not None:
            materialized[attribute["column"]] = _decoded_branch_attribute(attribute, stored)
        elif occurrence is not None:
            materialized[occurrence["column"]] = stored
    return materialized


def _decoded_branch_attribute(attribute: Mapping[str, Any], stored: Any) -> Any:
    """One branch document's top-level Attribute as the read publishes it: a
    scalar collection decodes element by element, or leaves its root
    unhydratable, as :func:`_decoded_leaf` judges one."""
    if not is_scalar_collection(attribute):
        return decode_leaf(attribute["type"], stored)
    try:
        return decode_collection(attribute["type"], stored)
    except DocumentEncodingError:
        return UnavailableLeaf(stored)


def _top_level_document_members(
    layout: TableLayout, entities: dict[str, Entity]
) -> Iterator[tuple[Entity, str, DocumentPath]]:
    """Each top-level member *layout* places in its document: the declaring
    Entity, the member name, and its placement."""
    for address, placement in layout.placements.items():
        if len(address.path) == 1 and isinstance(placement, DocumentPath):
            yield entities[address.owner], address.path[0], placement
