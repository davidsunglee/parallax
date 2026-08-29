"""Turning the physical rows a golden statement returned into the logical result.

The golden SQL projects storage: a raw discriminator column, a shared Structured
Column, a per-branch ``family_variant`` literal, typed ``null`` placeholders. None
of those is a result field. This module derives the result the case authored from
them — ``familyVariant`` from the tag metadata map, a Relational Document Layout's
members from the document it was stored in — and asserts the projection shape each
derivation depends on, reading that shape from the golden text so a zero-row read
still witnesses a dropped column.

The physical facts themselves are never re-derived here: family topology comes
from :mod:`..inheritance`, column placement from :mod:`..storage_layout`, and the
JSON codec from :mod:`..document_codec`. A table-per-concrete-subtype read's
`union all` is graded by :mod:`.tpcs` before its rows are materialized, since what
that statement must say is a property of the layout rather than of any row.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, NamedTuple

from ..case import Case, Entity
from ..case_assertions import CaseFailure
from ..document_codec import decode_leaf, decode_stored
from ..inheritance import (
    STRATEGY_TPCS,
    STRATEGY_TPH,
    Family,
    is_abstract,
    tag_value_to_subtype,
)
from ..storage_layout import (
    DocumentPath,
    MemberAddress,
    RelationalDocument,
    TableLayout,
    member_address,
    position_projection,
    position_view,
)
from . import tpcs
from .execute import (
    golden_projection_columns,
)

# --- materialized rows ------------------------------------------------------


class MaterializedRow(dict[str, Any]):
    """A result row that still remembers which of its columns are raw VO blobs.

    ``value_object_columns`` are the columns carrying an undecoded Value Object
    occurrence; ``consumed_value_object_columns`` are the ones a projection has
    already taken, so an identity-only comparison can drop the rest.
    """

    __slots__ = ("consumed_value_object_columns", "value_object_columns")

    def __init__(
        self,
        values: dict[str, Any],
        *,
        value_object_columns: dict[str, Any] | None = None,
        consumed_value_object_columns: set[str] | None = None,
    ) -> None:
        super().__init__(values)
        self.value_object_columns = value_object_columns or {}
        self.consumed_value_object_columns = consumed_value_object_columns or set()


def _materialized_row(row: dict[str, Any]) -> MaterializedRow:
    """A writable copy of *row* preserving any Value Object bookkeeping it carries."""
    if isinstance(row, MaterializedRow):
        return MaterializedRow(
            dict(row),
            value_object_columns=dict(row.value_object_columns),
            consumed_value_object_columns=set(row.consumed_value_object_columns),
        )
    return MaterializedRow(dict(row))


def reference_identity_row(row: dict[str, Any]) -> dict[str, Any]:
    """*row* reduced to the identity a ``referenceSql`` oracle can be compared to.

    An undecoded Value Object occurrence is dropped, because the independent
    oracle selects the matched row SET rather than re-deriving the document; an
    occurrence a projection already consumed stays, since the column then carries a
    materialized value rather than the raw blob.
    """
    if not isinstance(row, MaterializedRow):
        return dict(row)
    return {
        key: value
        for key, value in row.items()
        if key not in row.value_object_columns or key in row.consumed_value_object_columns
    }


def coerce_identity_key(value: Any) -> Any:
    """Coerce a DB / expected scalar to an exact hashable identity-key form.

    Used only by deep-fetch key gathering, bucket lookup, and node identity.
    Projected graph values must keep their original types so graph equality can
    compare numerics exactly via :func:`..case_assertions.scalars_equal`.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else value
    if isinstance(value, float):
        return Decimal(str(value))
    return value


# --- the read's family position ---------------------------------------------


class _AbstractFamilyPosition(NamedTuple):
    """The abstract family node a query reads, with the family it belongs to.

    *target* keeps the QUERY's own spelling of that position — every :class:`Family`
    lookup resolves an unambiguous local alias itself, so carrying the authored
    spelling keeps a consumer's diagnostics in the case's own words.
    """

    family: Family
    target: str
    strategy: str | None


def abstract_family_position(case: Case, query: Any) -> _AbstractFamilyPosition | None:
    """Classify *query*'s target position: the abstract family node it reads, or
    ``None`` for every other read.

    One classifier for every consumer whose behavior turns on the distinction,
    because they all ask the same question of the same field. An ABSTRACT position
    resolves over more than one concrete subtype, so its SQL partitions per branch
    and its result carries a variant tag (`m-sql`); a CONCRETE-target read — and any
    read of a non-inheritance entity — carries neither, having already named the one
    variant it returns. What differs between consumers is only the storage
    *strategy* they then project that behavior from.

    Abstractness is read off the definition's inheritance role, which only a family
    participant carries, so a non-inheritance target answers ``None`` by the same
    test.
    """
    target = query.get("target") if isinstance(query, dict) else None
    if not isinstance(target, str):
        return None
    family = Family(case.model.entity_defs)
    if target not in family.defs:
        return None
    if not is_abstract(family.defs[target]):
        return None
    return _AbstractFamilyPosition(family, target, family.strategy_of(target))


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


# --- Relational Document Layout ---------------------------------------------


class DocumentMember(NamedTuple):
    """One member a Relational Document Layout keeps inside the shared Structured
    Column: where it sits in the document and — for a leaf — the declared type its
    stored spelling decodes through.

    ``address`` identifies the member — by its declaring owner, so two disjoint
    inheritance siblings sharing a Table may reuse a member name and still be told
    apart — and ``column`` only spells it: a member inside a document claims no
    Column, so its spelling is free to collide with the Column a direct member
    really holds."""

    address: MemberAddress
    column: str
    path: tuple[str, ...]
    type_spelling: str | None

    @property
    def name(self) -> str:
        return self.address.path[0]


def document_layout_members(case: Case, entity: Entity) -> tuple[str, tuple[DocumentMember, ...]]:
    """*entity*'s Structured Column and the top-level members it carries.

    Answers ``("", ())`` for a conventional ``Columns`` entity, which is what makes
    the fan-out below inert rather than conditional at its call sites. Residency
    comes from the independently compiled Member Placements, never from the
    declaration, and each member is asked for at its own address: a Table shared by
    disjoint inheritance siblings holds a placement per declaration, so the member
    one of them reaches under a reused name is the one its own declaration owns. A
    leaf inside an occurrence is addressed under that occurrence and is left to the
    occurrence's own document, which already carries it.
    """
    layout = case.model.storage_layout.table(entity.table)
    if layout is None:
        return "", ()
    slot = next(
        (slot for slot in layout.columns if isinstance(slot.contributor, RelationalDocument)), None
    )
    if slot is None:
        return "", ()
    family = Family(case.model.entity_defs)

    def resident(declaration: dict[str, Any], type_spelling: str | None) -> DocumentMember | None:
        address = member_address(family, entity.canonical_name, declaration["name"])
        placement = layout.placement(address)
        if not (isinstance(placement, DocumentPath) and placement.slot == slot):
            return None
        return DocumentMember(address, declaration["column"], placement.path, type_spelling)

    declared = (
        *((attribute, attribute["type"]) for attribute in entity.attributes),
        *((occurrence, None) for occurrence in entity.value_objects),
    )
    return slot.column, tuple(
        member
        for declaration, type_spelling in declared
        if (member := resident(declaration, type_spelling)) is not None
    )


def _document_value(document: Any, path: tuple[str, ...]) -> Any:
    """The raw stored value at *path*, or ``None`` where the walk stops."""
    current = document
    for name in path:
        if not isinstance(current, dict) or name not in current:
            return None
        current = current[name]
    return current


def materialize_document_layout(
    case: Case,
    entity: Entity,
    rows: list[dict[str, Any]],
    *,
    include_value_objects: bool,
) -> list[dict[str, Any]]:
    """Fan a Relational Document Layout read's Structured Column out into the members
    it was asked for, under the result names a ``Columns`` layout would have used.

    The same shape as :func:`materialize_family_variant`: the golden SQL projects a
    raw column and the logical result is derived from it here, because the Structured
    Column is never itself a result field (`m-sql`). Which members a read asked for
    is the result form's answer — a row-form read takes the scalars alone while an
    instance form additionally carries every applicable occurrence — so the caller
    states it rather than this deriving a second projection rule of its own.

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
    column, members = document_layout_members(case, entity)
    if not column:
        return rows
    selected = [
        member for member in members if include_value_objects or member.type_spelling is not None
    ]
    materialized: list[dict[str, Any]] = []
    for row in rows:
        if column not in row:
            return rows
        document = decode_stored(row[column])
        node = {key: value for key, value in row.items() if key != column}
        for member in selected:
            stored = _document_value(document, member.path)
            node[member.column] = (
                stored
                if member.type_spelling is None
                else decode_leaf(member.type_spelling, stored)
            )
        materialized.append(node)
    return materialized


def _materialize_target_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """:func:`materialize_document_layout` over the case's own read target.

    A top-level read's rows belong to its query's own ``target``; a deep fetch's
    child level does not, which is why the entity is an argument there and resolved
    here.
    """
    target_name = case.object_query.get("target")
    if not isinstance(target_name, str):
        return rows
    return materialize_document_layout(
        case,
        case.model.entity(target_name),
        rows,
        include_value_objects=include_value_objects,
    )


def materialize_target_tph_document_layout(
    case: Case, rows: list[dict[str, Any]], *, include_value_objects: bool
) -> list[dict[str, Any]]:
    """Decode an abstract TPH document only after its raw tag resolves the variant."""
    position = abstract_family_position(case, case.object_query)
    if position is None or position.strategy != STRATEGY_TPH:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )
    family, target_name = position.family, position.target
    target = case.model.entity(target_name)
    column, _members = document_layout_members(case, target)
    if not column:
        return _materialize_target_document_layout(
            case, rows, include_value_objects=include_value_objects
        )

    tagged = materialize_family_variant(case, rows)
    effective = read_effective_set(case, family, target_name)
    scalar_superset = {
        member.column
        for concrete in effective
        for member in document_layout_members(case, case.model.entity(concrete))[1]
        if member.type_spelling is not None
    }
    materialized: list[dict[str, Any]] = []
    for row in tagged:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            materialized.append(row)
            continue
        (decoded,) = materialize_document_layout(
            case,
            case.model.entity(variant),
            [row],
            include_value_objects=include_value_objects,
        )
        if not include_value_objects:
            for column_name in scalar_superset:
                decoded.setdefault(column_name, None)
        materialized.append(decoded)
    return materialized


# --- familyVariant ----------------------------------------------------------


def materialize_family_variant(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialize ``familyVariant`` for an abstract-target table-per-hierarchy read.

    A non-inheritance / concrete-target read (or a non-TPH strategy) returns *rows*
    unchanged. For an abstract target the golden SQL projects the raw tag column and
    the full concrete superset; this asserts that projection shape, then replaces the
    tag column with the derived ``familyVariant`` (``tagValue`` -> concrete subtype
    name) so the materialized rows can be compared to ``then.rows``.
    """
    position = abstract_family_position(case, case.object_query)
    if position is None:
        return rows  # concrete-target (or non-inheritance) read carries no familyVariant
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


def materialize_step_family_variant(
    case: Case, step: Mapping[str, Any], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Materialize ``familyVariant`` for a step whose OWN read targets an abstract position.

    A step's ``expectRows`` states the leaves that read materialized, and an
    abstract-target read's leaf carries the derived variant rather than the raw
    tag column its SQL projects (`m-case-format` *Read targeting*). The position
    is classified from the STEP's own query, because a Scenario names one target
    per step and none for the case.
    """
    position = abstract_family_position(case, step.get("objectQuery"))
    if position is None:
        return rows
    family, target_name = position.family, position.target
    if position.strategy == STRATEGY_TPCS:
        return _materialize_tpcs_family_variant(case, rows, family, target_name)
    if position.strategy != STRATEGY_TPH:
        return rows
    return _materialize_tph_family_variant(case, family, target_name, rows)


def _materialize_tph_family_variant(
    case: Case, family: Family, target_name: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Replace each row's raw tag column with the derived ``familyVariant``.

    The row-level half of the table-per-hierarchy materialization, shared by the
    whole-read path (which asserts the golden projection shape first) and the
    per-step one (whose shape its own step golden fixes).
    """
    tag_column = family.tag_column_of(target_name)
    if tag_column is None:
        return rows
    if rows and all("familyVariant" in row and tag_column not in row for row in rows):
        return rows
    variant_map = tag_value_to_subtype(case.model.entity_defs)
    return [
        _with_family_variant(
            case,
            _materialized_row(row),
            tag_column=tag_column,
            variant_map=variant_map,
            subject="abstract-target read",
        )
        for row in rows
    ]


def _with_family_variant(
    case: Case,
    row: dict[str, Any],
    *,
    tag_column: str,
    variant_map: Mapping[Any, str],
    subject: str,
) -> dict[str, Any]:
    """*row* with its raw tag column replaced by the ``familyVariant`` the tag names.

    The one tag-to-variant transformation, applied wherever a row arrives carrying a
    table-per-hierarchy discriminator. *row* is transformed IN PLACE, so a caller hands
    over a private copy and chooses its form — a :class:`MaterializedRow` whose Value
    Object bookkeeping must survive, or a plain row. *subject* names the read in both
    diagnostics, since a whole-read tag failure and a deep-fetch hop's are the same
    defect reported against different reads.
    """
    if tag_column not in row:
        raise CaseFailure(
            f"{case.path.name}: {subject} does not project the tag column "
            f"{tag_column!r}; familyVariant cannot be materialized (m-inheritance)."
        )
    tag_value = row.pop(tag_column)
    variant = variant_map.get(tag_value)
    if variant is None:
        raise CaseFailure(
            f"{case.path.name}: {subject} tag value {tag_value!r} maps to no concrete "
            f"subtype (tag metadata {sorted(variant_map)})."
        )
    if isinstance(row, MaterializedRow) and "familyVariant" in row:
        row.consumed_value_object_columns.add("familyVariant")
    row["familyVariant"] = variant
    return row


def materialize_hop_variant(
    case: Case,
    row: dict[str, Any],
    *,
    view_key: str,
    tag_column: str,
    variant_map: Mapping[Any, str],
) -> dict[str, Any]:
    """Replace a polymorphic deep-fetch child row's raw tag column with ``familyVariant``.

    The table-per-hierarchy analogue of :func:`materialize_family_variant` for a
    deep-fetch hop, whose own step golden fixes the projection shape a whole read has
    to assert first. The hop states its own facts — its attach key, its tag column, and
    the family's tag map — rather than handing over the fetch step it belongs to,
    because the hop is the caller's vocabulary and the derivation is this module's.
    """
    return _with_family_variant(
        case,
        dict(row),
        tag_column=tag_column,
        variant_map=variant_map,
        subject=f"polymorphic hop {view_key}",
    )


def narrow_to_variant_columns(case: Case, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Narrow each row of an INSTANCE-FORM abstract-target read to its own concrete
    variant's declared columns (m-case-format "Read targeting", the instance-form
    per-variant node shape).

    A materialized instance carries only its own branch's members — its inherited
    chain plus its own declared attributes — never a sibling branch's null-padded
    column: a `Dog` node has no `indoor` key to be null. Row-form (`then.rows`)
    keeps the full concrete-superset row unchanged (:func:`materialize_family_variant`
    alone); this ADDITIONAL narrowing applies only where a row already carries a
    materialized ``familyVariant`` (a no-op for a concrete-target read, or a
    non-inheritance entity, whose rows carry none).
    """
    family = Family(case.model.entity_defs)
    narrowed: list[dict[str, Any]] = []
    for row in rows:
        variant = row.get("familyVariant")
        if not isinstance(variant, str):
            narrowed.append(row)
            continue
        own_columns = set(position_projection(case.model.storage_layout, family, [variant]))
        own_columns.update(
            member.column for member in document_layout_members(case, case.model.entity(variant))[1]
        )
        narrowed.append(
            MaterializedRow(
                {
                    key: value
                    for key, value in row.items()
                    if key == "familyVariant" or key in own_columns
                },
                value_object_columns=(
                    dict(row.value_object_columns) if isinstance(row, MaterializedRow) else None
                ),
                consumed_value_object_columns=(
                    set(row.consumed_value_object_columns)
                    if isinstance(row, MaterializedRow)
                    else None
                ),
            )
        )
    return narrowed


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
        if attribute["name"] in source:
            node[attribute["name"]] = decode_leaf(attribute["type"], source[attribute["name"]])
    for nested in occurrence.get("valueObjects", []):
        if _publishes_when_omitted(nested) or nested["name"] in source:
            node[nested["name"]] = _project_value_object(nested, source.get(nested["name"]))
    return node


def _publishes_when_omitted(nested: dict[str, Any]) -> bool:
    return nested.get("multiplicity", "one") == "many" or not nested.get("nullable", False)


def materialize_owner_node(entity: Entity, row: dict[str, Any]) -> dict[str, Any]:
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
        raw = (
            row.value_object_columns[column]
            if isinstance(row, MaterializedRow) and column in row.value_object_columns
            else node.pop(column)
        )
        if column in node and (
            not isinstance(row, MaterializedRow) or column not in row.consumed_value_object_columns
        ):
            node.pop(column)
        node[occurrence["name"]] = _project_value_object(occurrence, decode_stored(raw))
    return node


def _has_document_resident_attribute(case: Case, entity: Entity) -> bool:
    """Whether the layout placed any of *entity*'s own Attributes inside its
    Structured Column — the one need that reaches a Relational Document Layout's
    shared Column from a row-form read (`m-sql` *Read projection*, rule 5)."""
    resident = {member.name for member in document_layout_members(case, entity)[1]}
    return any(attribute["name"] in resident for attribute in entity.attributes)


def _materialize_tpcs_family_variant(
    case: Case, rows: list[dict[str, Any]], family: Family, target_name: str
) -> list[dict[str, Any]]:
    """Rename the projected `familyVariant` literal column for a TPCS abstract read.

    Asserts the `union all` branch/projection shape, then renames each row's
    ``family_variant`` (the per-branch subtype-name literal) to ``familyVariant`` so
    the materialized rows compare against ``then.rows`` — the TPCS counterpart of the
    TPH tag-to-variant materialization (m-inheritance / m-sql). A row observed through
    a collision-safe internal alias is restored to the physical spelling its OWN
    branch's slot carries, and an alias standing for a slot that branch does not own is
    dropped.
    """
    effective = read_effective_set(case, family, target_name)
    ordered = family.canonical_concrete_order(effective)
    view = position_view(case.model.storage_layout, family, effective)
    if view is None:
        raise CaseFailure(
            f"{case.path.name}: the storage layout resolves no position for the effective "
            f"concrete set {ordered}; a table-per-concrete-subtype abstract read must map "
            f"onto one family's canonical concrete selection."
        )
    branch_variants = tpcs.branch_variants(case, family, ordered, view)
    document_resident = any(
        _has_document_resident_attribute(case, case.model.entity(name))
        for _branch, name in branch_variants
    )
    tpcs.assert_union_shape(case, view, branch_variants, document_resident=document_resident)
    ordinals = tpcs.projected_position_ordinals(case, view, document_resident=document_resident)
    superset = [view.column_spellings[ordinal] for ordinal in ordinals]
    result_aliases = tpcs.result_aliases(superset)
    column_counts = {column: superset.count(column) for column in set(superset)}
    slots_by_variant = {
        name: tuple(branch.slots[ordinal] for ordinal in ordinals)
        for branch, name in branch_variants
    }
    layouts_by_variant = {name: branch.layout for branch, name in branch_variants}

    materialized: list[dict[str, Any]] = []
    for row in rows:
        new_row = _materialized_row(row)
        if tpcs.VARIANT_COLUMN not in new_row:
            raise CaseFailure(
                f"{case.path.name}: table-per-concrete-subtype abstract read does not "
                f"project the {tpcs.VARIANT_COLUMN!r} literal; familyVariant cannot be "
                f"materialized (m-sql)."
            )
        if "familyVariant" in new_row:
            new_row.consumed_value_object_columns.add("familyVariant")
        variant = new_row.pop(tpcs.VARIANT_COLUMN)
        slots = slots_by_variant.get(variant)
        if slots is None:
            raise CaseFailure(
                f"{case.path.name}: {tpcs.VARIANT_COLUMN!r} literal {variant!r} names no "
                f"branch of the effective concrete set {sorted(slots_by_variant)}."
            )
        for slot, column, result_alias in zip(slots, superset, result_aliases, strict=True):
            if (
                result_alias in new_row
                and result_alias != column
                and (column_counts[column] == 1 or slot is not None)
            ):
                new_row[column] = new_row.pop(result_alias)
            elif column_counts[column] > 1 and slot is None:
                new_row.pop(result_alias, None)
        new_row["familyVariant"] = variant
        new_row = _materialize_tpcs_document_row(case, layouts_by_variant[variant], new_row)
        materialized.append(new_row)
    return materialized


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
        for address, placement in candidate.placements.items():
            if len(address.path) != 1 or not isinstance(placement, DocumentPath):
                continue
            declaration = entities[address.owner]
            name = address.path[0]
            attribute = next(
                (item for item in declaration.attributes if item["name"] == name), None
            )
            if attribute is not None:
                materialized.setdefault(attribute["column"], None)
    for address, placement in layout.placements.items():
        if len(address.path) != 1 or not isinstance(placement, DocumentPath):
            continue
        entity = entities[address.owner]
        name = address.path[0]
        attribute = next((item for item in entity.attributes if item["name"] == name), None)
        occurrence = next((item for item in entity.value_objects if item["name"] == name), None)
        stored = _document_value(document, placement.path)
        if attribute is not None:
            materialized[attribute["column"]] = decode_leaf(attribute["type"], stored)
        elif occurrence is not None:
            materialized[occurrence["column"]] = stored
    return materialized
