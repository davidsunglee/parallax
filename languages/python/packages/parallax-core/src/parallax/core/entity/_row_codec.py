"""The Entity Row Codec — one model-bound authoring codec (spec §5).

Exposed from ``parallax.core.entity`` and deliberately **not** from top-level
``parallax.core``: it is the seam a write path derives rows through, not
developer surface.

Three operations answer one question each — every member the caller populated,
the identity, and the effective caller-authored changes — and a consumer asking
for one learns nothing about Pydantic, the private Change Record slot, physical
column names, temporal planning, or Audit Provenance. It is an **authoring**
codec: it emits only what a caller authored, never computes or stamps a
framework-owned value, and is never an Audit Provenance extension point
(ADR 0037). Its dependencies are the accepted Metamodel and the value's own
class, and nothing else.

Input validation **resolves; it does not own.** The codec resolves the Entity
Identity the value's class declares and refuses at resolution only when its model
declares no such Entity, so a value from another model whose identity this model
also declares reaches the member rule rather than a resolution refusal: the row
is a function of the resolved identity's declared members alone. The Entity
Identity/Entity Class index is never consulted, which is also why a model
composing no class at all reaches a fully functional codec.

**The candidate set is the model's; the selection is the operation's.** The
model's family-effective metadata supplies the candidates, their canonical keys,
and their order; each operation then selects from those candidates by its own
rule, and :data:`ENTITY_ROW_MEMBER_MISSING` reaches an operation's own selection
and nothing else. It names one harm from either side of that pairing: the
resolved identity declares no such member, so no canonical key names it, or the
value's class carries no attribute for one it does declare. Both leave the
operation unable to emit a member its selection claims, and a row is never
emitted short of one.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

from parallax.core.entity._declaration import declaration_of, is_entity_class
from parallax.core.entity._entity import CHANGE_RECORD_SLOT, Entity, WireNames, wire_names_of
from parallax.core.entity._errors import (
    ENTITY_ROW_MALFORMED_PROVENANCE,
    ENTITY_ROW_MEMBER_MISSING,
    ENTITY_ROW_NO_CHANGE_RECORD,
    ENTITY_ROW_NOT_AN_ENTITY,
    ENTITY_ROW_TARGET_NOT_IN_MODEL,
    EntityRowError,
)
from parallax.core.entity._expressions import serialize_member
from parallax.core.entity._model import DomainModel, model_of
from parallax.core.inheritance import view as inheritance_view
from parallax.core.metamodel import (
    AttributeMetadata,
    EntityIdentity,
    Metamodel,
    PrimaryKey,
    ValueObjectMetadata,
)

__all__ = ["EntityRowCodec", "row_codec_of"]


_NO_RECORD: Final = object()
"""Distinguishes an absent Change Record slot from one holding anything at all,
which is what tells the two provenance refusals apart."""


@dataclass(frozen=True, slots=True)
class _RowFacts:
    """One Entity Identity's row facts, derived once from accepted metadata.

    Family-effective throughout: an inherited member reaches a concrete subtype
    as its own candidate, so ``members`` is the whole family-effective candidate
    set, and its order is the order every row it keys is emitted in. That order
    is by category — Attributes in declaration order, base-first, then top-level
    Value Objects in theirs — chosen rather than incidental: an authored
    interleaving of the two is recoverable only from the value's class, and a
    row's keys are a function of the model alone.
    """

    identity: EntityIdentity
    members: Mapping[str, AttributeMetadata | ValueObjectMetadata]
    framework_owned: frozenset[str]
    primary_key: tuple[str, ...]


class EntityRowCodec:
    """One Domain Model's row-derivation collaboration.

    Per accepted Metamodel rather than per row: it is the home of the per-Entity
    facts derived once from that metadata — the family-effective candidate set,
    its canonical order, the framework-owned designation, and the primary key.
    Because it is reached through :func:`row_codec_of`, no operation takes a
    model argument and none can be handed a mismatched one.

    It is stated over the accepted Metamodel rather than over the
    :class:`~parallax.core.entity.DomainModel` that carries one, because that is
    the whole of what a row depends on: a model composing no Entity Class
    derives rows exactly as one composing every class does.
    """

    __slots__ = ("_cache", "_model")

    def __init__(self, model: Metamodel) -> None:
        self._model = model
        self._cache: dict[EntityIdentity, _RowFacts] = {}

    def full_row(self, value: object) -> dict[str, object]:
        """Every member ``value`` populated, keyed by canonical name.

        The selection is what ``model_fields_set`` reports as populated, so a
        member the caller never set is omitted and the narrower insert is
        emitted. A framework-owned member is omitted rather than refused: a
        hydrated value carries stored state there, and emitting it would launder
        that state into a caller assignment.
        """
        facts, names = self._resolved(value)
        populated = cast("Entity", value).model_fields_set
        selected = frozenset(
            canonical for py_name, canonical in names.py_to_name.items() if py_name in populated
        )
        self._require_declared(facts, selected, "full_row")
        return self._serialized(facts, names, value, selected, "full_row")

    def identity_row(self, value: object) -> dict[str, object]:
        """``value``'s primary-key members, keyed by canonical name.

        Its values are **raw** where :meth:`full_row` and :meth:`edited_row`
        carry serialized ones — a deliberately preserved asymmetry rather than
        an accident. Its selection is the resolved identity's own declared
        primary key, so it names no candidate the metadata did not supply; a
        cross-model value whose own class keys the same Entity by other members
        carries no attribute to read one from, and that is refused rather than
        dropped, because an unkeyed row is no identity row.
        """
        facts, names = self._resolved(value)
        return self._identity_row(facts, names, value, "identity_row")

    def edited_row(self, value: object) -> dict[str, object] | None:
        """``value``'s identity plus its effective caller-authored changes, or
        ``None`` when the edit nets to zero.

        Requires accepted Edited Copy provenance. A member the edit chain
        touched drops out when its current value equals the original the chain
        first recorded, so a net-zero chain answers ``None`` and "nothing to
        write" has exactly one representation.

        Refusal follows selection, and effectiveness is weighed afterwards: a
        recorded name the resolved identity does not declare is refused even
        when the edit that touched it restored the original value, because what
        the rule protects is a selection the codec cannot key.
        """
        facts, names = self._resolved(value)
        record = _change_record(facts, value)
        touched = {
            names.py_to_name.get(py_name, py_name): (py_name, original)
            for py_name, original in record.items()
        }
        self._require_declared(facts, touched, "edited_row")
        effective = frozenset(
            canonical
            for canonical, (py_name, original) in touched.items()
            if not _assignment_matches_original(getattr(value, py_name), original)
        )
        if not effective:
            return None
        row = self._identity_row(facts, names, value, "edited_row")
        row.update(self._serialized(facts, names, value, effective, "edited_row"))
        return row

    # --- resolution and the shared emission ------------------------------- #

    def _resolved(self, value: object) -> tuple[_RowFacts, WireNames]:
        """``value``'s row facts and its class's own name correspondences."""
        cls = type(value)
        if not is_entity_class(cls):
            raise EntityRowError(
                code=ENTITY_ROW_NOT_AN_ENTITY,
                message=(
                    f"{cls.__name__} is not a Parallax Entity Class, so its values carry no "
                    "Entity Identity to derive a row for"
                ),
            )
        return self._facts(declaration_of(cls).identity), wire_names_of(cls)

    def _facts(self, identity: EntityIdentity) -> _RowFacts:
        """``identity``'s derived row facts, computed once per model."""
        cached = self._cache.get(identity)
        if cached is not None:
            return cached
        metadata = self._model.entity(identity)
        if metadata is None:
            raise EntityRowError(
                code=ENTITY_ROW_TARGET_NOT_IN_MODEL,
                message=(
                    f"this model declares no Entity {identity.canonical!r}; the identical value "
                    "derives a row against a model that declares it"
                ),
                identity=identity,
            )
        position = inheritance_view(self._model).entity(identity)
        attributes = (
            tuple(metadata.declared_attributes)
            if position is None
            else tuple(position.applicable_attributes)
        )
        occurrences = (
            tuple(metadata.declared_value_objects)
            if position is None
            else tuple(position.applicable_value_objects)
        )
        members: dict[str, AttributeMetadata | ValueObjectMetadata] = {
            attribute.identity.name: attribute for attribute in attributes
        }
        members.update({occurrence.identity.path[-1]: occurrence for occurrence in occurrences})
        facts = _RowFacts(
            identity=identity,
            members=MappingProxyType(members),
            framework_owned=frozenset(
                attribute.identity.name for attribute in attributes if attribute.framework_owned
            ),
            primary_key=tuple(
                attribute.identity.name
                for attribute in attributes
                if isinstance(attribute.primary_key, PrimaryKey)
            ),
        )
        self._cache[identity] = facts
        return facts

    def _require_declared(self, facts: _RowFacts, selected: Iterable[str], operation: str) -> None:
        """Refuse a selection naming a member the resolved identity does not declare."""
        undeclared = sorted(name for name in selected if name not in facts.members)
        if not undeclared:
            return
        named = ", ".join(repr(name) for name in undeclared)
        raise EntityRowError(
            code=ENTITY_ROW_MEMBER_MISSING,
            message=(
                f"{operation} selects {named}, which {facts.identity.canonical} does not "
                "declare: no canonical key names it, and dropping a value the caller authored "
                "would signal nothing"
            ),
            identity=facts.identity,
        )

    def _require_supplied(
        self, facts: _RowFacts, names: WireNames, emitted: Iterable[str], operation: str
    ) -> dict[str, str]:
        """``emitted``'s canonical-to-Python names, refusing one the value cannot
        supply.

        The resolved identity decides what a candidate is; the value's class
        decides what can be read for one. Those two are the same class only for a
        value of this model's own: a cross-model value resolves through an
        identity this model also declares, and its class's own declaration of
        that Entity is free to name the members otherwise — so a selection can
        name a member no attribute of the value answers.
        """
        supplied = {
            canonical: names.name_to_py[canonical]
            for canonical in emitted
            if canonical in names.name_to_py
        }
        unsupplied = sorted(canonical for canonical in emitted if canonical not in supplied)
        if unsupplied:
            named = ", ".join(repr(name) for name in unsupplied)
            raise EntityRowError(
                code=ENTITY_ROW_MEMBER_MISSING,
                message=(
                    f"{operation} selects {named}, which this {facts.identity.canonical} value's "
                    "class does not carry: its own declaration of that Entity names those members "
                    "otherwise, and a row short of what its selection claims would signal nothing"
                ),
                identity=facts.identity,
            )
        return supplied

    def _identity_row(
        self, facts: _RowFacts, names: WireNames, value: object, operation: str
    ) -> dict[str, object]:
        py_names = self._require_supplied(facts, names, facts.primary_key, operation)
        return {canonical: getattr(value, py_names[canonical]) for canonical in facts.primary_key}

    def _serialized(
        self,
        facts: _RowFacts,
        names: WireNames,
        value: object,
        selected: frozenset[str],
        operation: str,
    ) -> dict[str, object]:
        """``selected``'s serialized values in the model's own candidate order.

        Iterating the candidates rather than the selection is what makes a row's
        key order a function of the model, never of the order a caller populated
        or edited members in.
        """
        emitted = tuple(
            canonical
            for canonical in facts.members
            if canonical in selected and canonical not in facts.framework_owned
        )
        py_names = self._require_supplied(facts, names, emitted, operation)
        return {
            canonical: serialize_member(getattr(value, py_names[canonical]))
            for canonical in emitted
        }


def row_codec_of(model: DomainModel) -> EntityRowCodec:
    """``model``'s row codec — the reach seam for it.

    One per Domain Model, created on first reach and retained by the model, so
    every write against one model shares the per-Entity facts derived from it.

    Created on first reach because this module sits above ``_model`` in §7's
    import DAG: a :class:`~parallax.core.entity.DomainModel` cannot construct one
    without inverting an edge the generated import contracts reject, so this
    function is the only place that can build one. The guard is a
    dependency-direction consequence, not a performance hedge.
    """
    codec = model._row_codec  # pyright: ignore[reportPrivateUsage] - first-party seam
    if not isinstance(codec, EntityRowCodec):
        codec = EntityRowCodec(model_of(model))
        model._row_codec = codec  # pyright: ignore[reportPrivateUsage] - first-party seam
    return codec


def _change_record(facts: _RowFacts, value: object) -> Mapping[str, object]:
    """``value``'s accepted Change Record, or the refusal its slot earns.

    The two refusals are told apart by the slot rather than by its contents: an
    absent slot is the ordinary plain, never-edited value, while a slot holding
    anything unreadable reports corruption of private first-party state.
    Collapsing the second into the first would name the wrong defect and leave
    the corruption unreported.
    """
    record = value.__dict__.get(CHANGE_RECORD_SLOT, _NO_RECORD)
    if record is _NO_RECORD:
        raise EntityRowError(
            code=ENTITY_ROW_NO_CHANGE_RECORD,
            message=(
                f"this {facts.identity.canonical} value carries no Change Record, so it names "
                "no change to write; derive an edited copy with `value.edit(**changes)`"
            ),
            identity=facts.identity,
        )
    if not _is_change_record(record):
        raise EntityRowError(
            code=ENTITY_ROW_MALFORMED_PROVENANCE,
            message=(
                f"this {facts.identity.canonical} value's Change Record slot holds "
                f"{type(record).__name__}, which names no touched member"
            ),
            identity=facts.identity,
        )
    return cast("Mapping[str, object]", record)


def _is_change_record(candidate: object) -> bool:
    """Whether the private slot holds a readable Change Record: a mapping from
    member names to the values they held when the chain first touched them."""
    return isinstance(candidate, dict) and all(
        isinstance(key, str) for key in cast("dict[object, object]", candidate)
    )


def _assignment_matches_original(assigned: object, original: object) -> bool:
    """Compare authored ``one`` members as a mask and ``many`` values as wholes.

    Mapping omission represents un-authored nested ``one`` state. Lists have no
    element identity, so their complete serialized elements must match rather
    than inheriting the mapping subset rule.
    """
    assigned_value = serialize_member(assigned)
    original_value = serialize_member(original)
    if isinstance(assigned_value, Mapping):
        if not isinstance(original_value, Mapping):
            return False
        assigned_items = cast("Mapping[object, object]", assigned_value)
        original_items = cast("Mapping[object, object]", original_value)
        return all(
            name in original_items and _assignment_matches_original(value, original_items[name])
            for name, value in assigned_items.items()
        )
    if isinstance(assigned_value, list):
        return isinstance(original_value, list) and assigned_value == original_value
    return assigned_value == original_value
