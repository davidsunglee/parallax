from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Final, Self, cast

from pydantic._internal._model_construction import ModelMetaclass

from parallax.core.base import FrozenMap, NeutralType, adopt_frozen_map
from parallax.core.document_codec import (
    MemberShape,
    Occurrence,
    OccurrenceCarrier,
    encode_leaf,
    encode_occurrence,
)
from parallax.core.entity._declaration import (
    FRAMEWORK_MINT,
    DeclarationKind,
    ValueObjectShape,
    build_class,
    shape_of,
)
from parallax.core.entity._edit import (
    Resolution,
    derive,
    unresolved_member_violation,
    use_edit,
)
from parallax.core.entity._errors import EditError, EditViolation, EntityDefinitionError
from parallax.core.entity._expressions import judged_edit_violation
from parallax.core.entity._instance_state import (
    BackedModel,
    is_present,
    plan_of,
)
from parallax.core.metamodel import (
    MODEL_ROOT,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    EntityIdentity,
    Multiplicity,
    ValueObjectMetadata,
    ValueObjectOccurrenceDeclaration,
    value_object_metadata,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["ValueObject", "ValueObjectMeta", "encode_value_object", "shape_of"]

_EDIT_RESOLUTION_SLOT: Final = "__parallax_value_object_edit_resolution__"


class ValueObjectMeta(ModelMetaclass):
    """The Value Object metaclass: the shared engine with no header vocabulary.

    The positionals are named ``cls_name``/``bases``/``ns`` and are
    positional-only for symmetry with the Entity metaclass, where ``name=`` and
    ``namespace=`` are header keywords that cannot also name a parameter.
    """

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type, ...],
        ns: dict[str, Any],
        /,
        *,
        _mint: object | None = None,
        **unknown: object,
    ) -> type:
        if unknown:
            raise EntityDefinitionError(
                code="entity-header-unknown-option",
                message=(
                    f"{cls_name}: a Value Object declares no class-header option "
                    f"({', '.join(sorted(unknown))})"
                ),
            )
        return build_class(
            mcs,
            cls_name,
            bases,
            cast("dict[str, object]", ns),
            kind=DeclarationKind.VALUE_OBJECT,
            mint=_mint,
            axes=(),
            header=None,
        )


class ValueObject(BackedModel, metaclass=ValueObjectMeta, _mint=FRAMEWORK_MINT):
    """The frozen base every Parallax Value Object Class extends.

    Instances are the only legal value for a Value Object member: a caller never
    assigns a raw mapping where an occurrence is declared.

    Every question about what a value physically holds is answered one level
    down, by :class:`~parallax.core.entity._instance_state.BackedModel`, exactly
    as it is for an Entity: a Value Object is published the same way.
    """

    __slots__ = ()

    if TYPE_CHECKING:
        # Declared for type checkers alone, and bound by nobody: Pydantic installs
        # a hash over each frozen class's own declared members at class creation,
        # which a checker cannot see, while `BaseModel` defining `__eq__` without
        # one is what would otherwise make every declared class statically
        # unhashable.

        def __hash__(self) -> int: ...

    def edit(self, **changes: object) -> Self:
        """The one door to an edited Value Object.

        The result is a validated copy carrying every member this value populates
        and the caller did not name, changing only what ``changes`` names — which
        is what makes the safe spelling of a nested change also the shortest one::

            customer.edit(address=customer.address.edit(city="Springfield"))

        Assigning an occurrence replaces its subtree whole, so restating a whole
        address to change one field is what deletes the fields the restatement
        forgets; this derives the new value from the old one instead.

        ``changes`` is validated by the SAME rules ``Entity.edit(**changes)`` and
        the serialized write boundary apply: every named member is resolved
        against this class's own declaration and judged by
        :func:`~parallax.core.metamodel.judge_assignment`, every violation is
        reported in one :class:`EditError` raised before anything is built, and
        the merged value then goes back through the ordinary constructor for the
        input policies. Four of the eight edit codes are unreachable here,
        because no Value Object member carries the designations that raise them
        (:func:`_member_metadata`).

        No Change Record is stamped and none is carried: provenance answers "what
        did this object's caller touch", and a Value Object has no identity and is
        never independently written — an occurrence reaches storage only as part
        of the Entity that contains it.

        Presence is carried forward exactly: a member this value never populated
        stays unpopulated, so it stays absent from the document rather than
        becoming an explicit null, and a member named as ``None`` becomes an
        explicit null. That distinction is what lets a value read from storage be
        written back unchanged.

        An edit with no changes is legal and builds nothing new to validate,
        because nothing was authored.
        """
        return derive(self, changes, _resolution_of(type(self)))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """Refused: ``edit(**changes)`` is the object-copy verb.

        ``model_copy(update=...)`` writes its values into the copy without
        validating them, so it can build a Value Object no declaration admits — a
        required member cleared, a leaf holding a value of another type — and a
        structurally invalid occurrence serializes into the stored document
        exactly as a valid one does. Assigning an occurrence replaces its subtree
        whole, so that document becomes the persisted truth.

        Refused with or without ``update=``, before any argument is examined.
        """
        del update, deep
        raise _use_edit(type(self), "model_copy") from None

    def copy(self, **kwargs: object) -> Self:
        """Refused: the deprecated Pydantic v1 shim reaches neither this class's
        name resolution nor the shared assignment judgement, so it is the same
        unvalidated door under an older name."""
        del kwargs
        raise _use_edit(type(self), "copy") from None

    def __copy__(self) -> Self:
        """Refused: one reachable copy path is enough to reinstate the bypass, and
        a shallow copy of the instance dictionary also carries the populated set
        that decides which members the document spells."""
        raise _use_edit(type(self), "__copy__") from None

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        """Refused for :meth:`__copy__`'s reason, plus deep-copied members."""
        del memo
        raise _use_edit(type(self), "__deepcopy__") from None

    def __parallax_document__(self) -> Mapping[str, object]:
        """This value as its canonical nested document.

        Named for the capability rather than exported as a protocol import, so
        the member serializer behind write rows and assignments can render a
        member without importing this frontend.
        """
        return _document(self)

    def __parallax_authoring_names__(self) -> Iterable[str]:
        """Canonical names this value authored, borrowed for write preparation."""
        declared = shape_of(type(self))
        bits = plan_of(type(self)).bits
        return (
            canonical
            for py_name, canonical in declared.py_to_name.items()
            if py_name in declared.many_py or is_present(self, bits[py_name])
        )

    def __parallax_authoring_member__(self, name: str, /) -> object:
        """One authored member in its live frontend carrier."""
        declared = shape_of(type(self))
        return getattr(self, declared.name_to_py[name])


def _use_edit(cls: type, door: str) -> EditError:
    """The refusal of an inherited copy path on a Value Object Class."""
    return use_edit(
        cls.__name__,
        door,
        location=MODEL_ROOT,
        remedy=(
            "derive an edited copy with `value.edit(**changes)`, the one door that judges "
            "every assignment — an unvalidated copy is structurally invalid data one write "
            "away from being stored"
        ),
    )


def _edit_violations(
    cls: type, shape: ValueObjectShape, changes: Mapping[str, object]
) -> tuple[EditViolation, ...]:
    """Every rule the authored ``changes`` break, one per named member.

    The split is ``Entity.edit``'s: resolving a Python name to a member is a
    class-shaped question answered here, and everything a resolved member then
    decides is the shared judgement's single verdict. A Value Object declares no
    relationships, so an unresolved name is the only resolution failure there is.

    Every named member is examined and contributes at most one violation, so a
    caller correcting several mistakes learns all of them at once.

    A Value Object Class is a reusable shape rather than a position in a model —
    the same class composes into occurrences of many Entities — so every
    violation locates at the model root. Locating at a member would have to name
    an occurrence, and this door reaches none.

    A nested occurrence stays in its live carrier while the shared authoring
    traversal judges it, so this surface and ``Entity.edit`` interpret one shape;
    the edit itself still merges the caller's own live value.
    """
    members = _member_metadata(cls, shape)
    violations: list[EditViolation] = []
    for py_name, value in changes.items():
        member = members.get(py_name)
        if member is None:
            violations.append(
                unresolved_member_violation(py_name, owner=cls.__name__, location=MODEL_ROOT)
            )
            continue
        violation = judged_edit_violation(member, value, owner=cls.__name__, location=MODEL_ROOT)
        if violation is not None:
            violations.append(violation)
    return tuple(violations)


def _resolution_of(cls: type) -> Resolution:
    """The Value Object-specific name resolution used by the shared derivation."""
    cached = cls.__dict__.get(_EDIT_RESOLUTION_SLOT)
    if isinstance(cached, Resolution):
        return cached

    shape = shape_of(cls)
    resolution = Resolution(
        declared=frozenset(shape.py_to_name),
        framework_owned=frozenset(),
        restores_presence=True,
        violations=lambda changes: _edit_violations(cls, shape, changes),
    )
    type.__setattr__(cls, _EDIT_RESOLUTION_SLOT, resolution)
    return resolution


def _member_metadata(
    cls: type, shape: ValueObjectShape
) -> dict[str, AttributeMetadata | ValueObjectMetadata]:
    """Each Python member name of ``cls`` to the Metadata that judges an assignment.

    The judgement reads a member's declared type, nullability, and — for an
    occurrence — its composite, and nothing else, which is what lets a Value
    Object Class supply it without belonging to any model. The two Entity-owned
    facts a Metadata value carries anyway are minted from the class itself: the
    owning identity is the class's own name, and a Storage Location is the
    member's canonical name. Neither reaches a caller, because a Value Object
    edit's violations locate at the model root and name the member.

    Four edit codes are unreachable through this door, and by construction rather
    than by omission. ``edit-relationship-member`` has no resolution to fire from,
    and ``edit-primary-key``, ``edit-read-only``, and ``edit-framework-owned``
    each report a designation ``m-value-object`` does not name — the declaration
    engine refuses ``primary_key=``/``read_only=`` on a Value Object member, and
    the framework-owned designation is derived from an Entity's version Attribute
    and As-Of Axes, which a Value Object has neither of.
    """
    owner = EntityIdentity(None, cls.__name__)
    members: dict[str, AttributeMetadata | ValueObjectMetadata] = {}
    for leaf in shape.shape.attributes:
        members[shape.name_to_py[leaf.name]] = AttributeMetadata(
            identity=AttributeIdentity(owner, leaf.name),
            type=leaf.type,
            storage=Column(leaf.name),
            nullable=leaf.nullable,
        )
    for nested in shape.shape.value_objects:
        members[shape.name_to_py[nested.name]] = value_object_metadata(
            owner,
            ValueObjectOccurrenceDeclaration(
                name=nested.name,
                storage=Column(nested.name),
                shape=nested.shape,
                multiplicity=nested.multiplicity,
                nullable=nested.nullable,
            ),
        )
    return members


def encode_value_object(value: ValueObject | None) -> Mapping[str, object] | None:
    """Encode a Value Object as its canonical nested document.

    ``None`` passes through unchanged (an absent occurrence). Filtered by member
    presence: a member the caller never populated is omitted rather than bound as
    an explicit null, which is the same explicit-versus-defaulted distinction a
    write row draws. A Many occurrence is
    the one exception — it is never nullable, and its empty default serializes as
    the empty array, the sole zero-element representation. Whether an omitted
    required member is a defect belongs to write validation, not to this
    serializer.

    Every leaf is spelled by ``m-document-codec``, never by this frontend and never by
    handing a runtime value to a JSON serializer, which is what left a ``Decimal``,
    ``bytes``, ``date``, ``time``, ``datetime``, or ``UUID`` leaf with no storage form.
    """
    if value is None:
        return None
    return _document(value)


def _document(value: ValueObject) -> Mapping[str, object]:
    shape = shape_of(type(value)).document_shape
    return cast(
        "Mapping[str, object]",
        encode_occurrence(
            value,
            shape,
            Multiplicity.ONE,
            _LIVE_VALUE_OBJECT,
            encode_leaf=_encode_value_object_leaf,
            build_object=_value_object_mapping,
            build_array=_value_object_sequence,
        ),
    )


_ABSENT_VALUE_OBJECT_MEMBER: Final = object()


def _value_object_values(record: object, shape: MemberShape) -> Iterable[object]:
    value = cast("ValueObject", record)
    declared = shape_of(type(value))
    bits = plan_of(type(value)).bits
    for member in shape.members:
        py_name = declared.name_to_py[member.name]
        if (
            isinstance(member, Occurrence) and member.multiplicity is Multiplicity.MANY
        ) or is_present(value, bits[py_name]):
            yield getattr(value, py_name)
        else:
            yield _ABSENT_VALUE_OBJECT_MEMBER


def _value_object_elements(value: object) -> Iterable[object]:
    return cast("tuple[ValueObject, ...]", value)


def _encode_value_object_leaf(neutral_type: NeutralType, value: object) -> object:
    if value is None:
        return None
    return encode_leaf(neutral_type, value)


def _value_object_mapping(
    entries: Iterable[tuple[str, object]],
) -> FrozenMap[str, object]:
    return adopt_frozen_map(dict(entries))


def _value_object_sequence(values: Iterable[object]) -> tuple[object, ...]:
    return tuple(values)


_LIVE_VALUE_OBJECT: Final = OccurrenceCarrier(
    absent=_ABSENT_VALUE_OBJECT_MEMBER,
    values=_value_object_values,
    elements=_value_object_elements,
)
