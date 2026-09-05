"""The Behavioral Impacts a model evolution derives.

The compatibility corpus witnesses each impact once, over non-temporal
standalone Entities and single-family hierarchies. What it does not reach
cheaply is what this covers: the facts a TEMPORAL family answers with, an impact
several operations contribute to, one operation moving a surviving Entity
between two families at once, the member impact an Entity-level change
deliberately dominates, and the two scenarios an authored descriptor cannot
spell at all — an As-Of Axis moving its endpoint Attributes, and the derived
primary-key Index changing underneath an unchanged authored one.

Every impact is read off the public result, and endpoint facts are compared as
whole values, because an impact reports a scope's facts rather than one field.
"""

from __future__ import annotations

import dataclasses

from _metamodel_support import Declaration, attribute, identity, instant, key, source

from parallax.core._formation_profile import form_metamodel
from parallax.core.base import STRING
from parallax.core.metamodel import (
    AbstractRoot,
    AbstractSubtype,
    AsOfAxisMetadata,
    AttributeIdentity,
    AttributeMetadata,
    Column,
    ConcreteSubtype,
    EntityIdentity,
    ExactEntityReference,
    IndexIdentity,
    IndexMetadata,
    Metamodel,
    PersistenceMode,
    Table,
    TablePerHierarchy,
    TemporalDimension,
)
from parallax.evolution.model_evolution import (
    LOCKING_FALLBACK,
    WRITES_DISABLED,
    AsOfAxisAdded,
    AsOfAxisAltered,
    AttributeAdded,
    AttributeAltered,
    AttributeRemoved,
    AttributeWriteCapability,
    BehavioralImpact,
    ConcreteSubtypeAdded,
    ConcurrencyControlChanged,
    EndAttributeChanged,
    EntityAltered,
    EntitySelectionFacts,
    EntityWriteShape,
    Evolution,
    IndexAdded,
    IndexAltered,
    IndexRemoved,
    QueryResultMembershipChanged,
    ScalarAdmissibility,
    StartAttributeChanged,
    TemporalAxisFacts,
    UniquenessEnforcementChanged,
    ValueAdmissibilityChanged,
    VersionGated,
    WriteCapabilityChanged,
    WritesEnabled,
    evolve,
)

_ROOT = identity("Instrument")
_BOND = identity("Bond")
_NOTE = identity("Note")
_STOCK = identity("Stock")
_ARRIVAL = identity("Arrival")
_LEDGER = identity("Ledger")
_ENTRY = identity("Entry")
_ARCHIVE = identity("Archive")

_VALID_TIME = AsOfAxisMetadata(
    TemporalDimension.VALID_TIME,
    AttributeIdentity(_ROOT, "validStart"),
    AttributeIdentity(_ROOT, "validEnd"),
)
_TRANSACTION_TIME = AsOfAxisMetadata(
    TemporalDimension.TRANSACTION_TIME,
    AttributeIdentity(_ROOT, "txStart"),
    AttributeIdentity(_ROOT, "txEnd"),
)
_ARRIVAL_AXIS = AsOfAxisMetadata(
    TemporalDimension.TRANSACTION_TIME,
    AttributeIdentity(_ARRIVAL, "txStart"),
    AttributeIdentity(_ARRIVAL, "txEnd"),
)
_FAMILY_AXES = (
    TemporalAxisFacts(
        TemporalDimension.VALID_TIME, _VALID_TIME.start_attribute, _VALID_TIME.end_attribute
    ),
    TemporalAxisFacts(
        TemporalDimension.TRANSACTION_TIME,
        _TRANSACTION_TIME.start_attribute,
        _TRANSACTION_TIME.end_attribute,
    ),
)


def _of[T: BehavioralImpact](evolution: Evolution, kind: type[T]) -> list[T]:
    return [impact for impact in evolution.behavioral_impacts if isinstance(impact, kind)]


def _temporal(*subtypes: EntityIdentity, writable: bool = True) -> Metamodel:
    """A BITEMPORAL table-per-hierarchy family beside a TRANSACTION-TIME
    standalone Entity, extended by ``subtypes`` and writable or not as a whole."""
    persistence = PersistenceMode.READ_WRITE if writable else PersistenceMode.READ_ONLY
    root = Declaration(
        identity=_ROOT,
        container=Table("instrument"),
        persistence=persistence,
        attributes=(
            key(_ROOT),
            instant(_ROOT, "validStart"),
            instant(_ROOT, "validEnd"),
            instant(_ROOT, "txStart"),
            instant(_ROOT, "txEnd"),
        ),
        as_of_axes=(_VALID_TIME, _TRANSACTION_TIME),
        inheritance=AbstractRoot(TablePerHierarchy("kind")),
    )
    arrival = Declaration(
        identity=_ARRIVAL,
        container=Table("arrival"),
        persistence=persistence,
        attributes=(key(_ARRIVAL), instant(_ARRIVAL, "txStart"), instant(_ARRIVAL, "txEnd")),
        as_of_axes=(_ARRIVAL_AXIS,),
    )
    concrete = [
        Declaration(
            identity=subtype,
            attributes=(attribute(subtype, f"{subtype.name.lower()}Amount"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), subtype.name.upper()),
        )
        for subtype in (_BOND, *subtypes)
    ]
    return form_metamodel(source(root, arrival, *concrete))


def test_a_selection_states_the_axes_of_the_temporal_shape_it_denotes() -> None:
    # A membership impact's endpoint facts are the concrete set AND the effective
    # Temporal Shape, named by its axes' own Attributes in canonical dimension
    # order — the whole predicate-free selection rule rather than the part that
    # changed.
    evolution = evolve(_temporal(), _temporal(_NOTE, _STOCK))
    (membership,) = _of(evolution, QueryResultMembershipChanged)
    assert membership.scope == _ROOT
    assert membership.earlier == EntitySelectionFacts((_BOND,), _FAMILY_AXES)
    assert membership.later == EntitySelectionFacts((_BOND, _NOTE, _STOCK), _FAMILY_AXES)


def test_one_impact_names_every_operation_that_contributed_to_it_once() -> None:
    # Two additions move one root's concrete set, so the single impact they cause
    # names both, deduplicated and in canonical operation order rather than in
    # the order the analyzer happened to reach them.
    evolution = evolve(_temporal(), _temporal(_NOTE, _STOCK))
    (membership,) = _of(evolution, QueryResultMembershipChanged)
    assert membership.caused_by == (ConcreteSubtypeAdded(_NOTE), ConcreteSubtypeAdded(_STOCK))


def test_a_temporal_write_surface_states_the_shape_its_axes_fix() -> None:
    # Persistence is family-wide, so withdrawing it reports every surviving WRITE
    # HANDLE of the family rather than the root that declared it — each with the
    # write shape its own axes fix, bitemporal for the family's concrete subtype
    # and Transaction-Time-only for the standalone Entity beside it. The abstract
    # root is a polymorphic read position that admitted no write to withdraw, so
    # its capability is Disabled at both endpoints and reports nothing.
    evolution = evolve(_temporal(), _temporal(writable=False))
    writes = _of(evolution, WriteCapabilityChanged)
    assert [impact.scope for impact in writes] == [_ARRIVAL, _BOND]
    assert [impact.earlier for impact in writes] == [
        WritesEnabled(EntityWriteShape.TRANSACTION_TIME_ONLY),
        WritesEnabled(EntityWriteShape.BITEMPORAL),
    ]
    assert [impact.later for impact in writes] == [WRITES_DISABLED] * 2


def _holding(*members: AttributeMetadata) -> Metamodel:
    return form_metamodel(
        source(
            Declaration(
                identity=_ARCHIVE,
                container=Table("archive"),
                attributes=(key(_ARCHIVE), *members),
            )
        )
    )


def test_only_a_surviving_position_reports_an_admissible_value_domain() -> None:
    # Two changes that are NOT admissibility impacts, beside the one that is: a
    # member arriving and leaving stays its own operation rather than becoming a
    # domain fact, and a member that only moved Column admits exactly what it
    # admitted before.
    note = attribute(_ARCHIVE, "note", type=STRING)
    assert evolve(_holding(), _holding(note)).behavioral_impacts == ()
    assert evolve(_holding(note), _holding()).behavioral_impacts == ()

    moved = dataclasses.replace(note, storage=Column("memo"))
    assert evolve(_holding(note), _holding(moved)).behavioral_impacts == ()

    widened = dataclasses.replace(note, nullable=True, max_length=64)
    (admissibility,) = _of(evolve(_holding(note), _holding(widened)), ValueAdmissibilityChanged)
    assert admissibility.scope == note.identity
    assert admissibility.earlier == ScalarAdmissibility(STRING, nullable=False, max_length=None)
    assert admissibility.later == ScalarAdmissibility(STRING, nullable=True, max_length=64)


def _versioned(*, declares_version: bool) -> Metamodel:
    revision = attribute(_LEDGER, "revision")
    members = (
        (key(_LEDGER), dataclasses.replace(revision, optimistic_locking=True))
        if declares_version
        else (key(_LEDGER),)
    )
    return form_metamodel(
        source(Declaration(identity=_LEDGER, container=Table("ledger"), attributes=members))
    )


def test_a_version_member_arriving_or_leaving_causes_the_concurrency_impact() -> None:
    # The version Attribute is added and removed here rather than altered, and a
    # member's arrival moves the Entity's gate exactly as flipping an existing
    # member's declaration does — so the impact's cause is that member's own
    # addition or removal.
    revision = AttributeIdentity(_LEDGER, "revision")
    arriving = evolve(_versioned(declares_version=False), _versioned(declares_version=True))
    (gained,) = _of(arriving, ConcurrencyControlChanged)
    assert (gained.scope, gained.earlier, gained.later) == (
        _LEDGER,
        LOCKING_FALLBACK,
        VersionGated(revision),
    )
    assert gained.caused_by == (AttributeAdded(revision),)

    leaving = evolve(_versioned(declares_version=True), _versioned(declares_version=False))
    (lost,) = _of(leaving, ConcurrencyControlChanged)
    assert (lost.earlier, lost.later) == (VersionGated(revision), LOCKING_FALLBACK)
    assert lost.caused_by == (AttributeRemoved(revision),)


def _two_families(*, moved: bool, extra: bool = False) -> Metamodel:
    """Two table-per-hierarchy families, one of them versioned, with `Bond`
    extending either one."""
    declarations = [
        Declaration(
            identity=_ROOT,
            container=Table("instrument"),
            attributes=(key(_ROOT),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_LEDGER,
            container=Table("ledger"),
            attributes=(
                key(_LEDGER),
                dataclasses.replace(attribute(_LEDGER, "revision"), optimistic_locking=True),
            ),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_STOCK,
            attributes=(attribute(_STOCK, "ticker", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "STOCK"),
        ),
        Declaration(
            identity=_ENTRY,
            attributes=(attribute(_ENTRY, "amount"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_LEDGER), "ENTRY"),
        ),
        Declaration(
            identity=_BOND,
            attributes=(attribute(_BOND, "coupon"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_LEDGER if moved else _ROOT), "BOND"),
        ),
    ]
    if extra:
        declarations.append(
            Declaration(identity=_ARRIVAL, container=Table("arrival"), attributes=(key(_ARRIVAL),))
        )
    return form_metamodel(source(*declarations))


def test_moving_a_position_between_families_moves_every_fact_that_family_fixes() -> None:
    # One operation, three impacts: the moved Entity answers a new family's
    # optimistic key, and BOTH roots denote a different concrete set. Every one
    # names that operation as its cause, and the Entity added beside it — which
    # moves nothing about any of these scopes — is named by none of them.
    evolution = evolve(_two_families(moved=False), _two_families(moved=True, extra=True))
    (moved,) = [
        operation for operation in evolution.operations if isinstance(operation, EntityAltered)
    ]
    (concurrency,) = _of(evolution, ConcurrencyControlChanged)
    assert (concurrency.scope, concurrency.earlier) == (_BOND, LOCKING_FALLBACK)
    assert concurrency.later == VersionGated(AttributeIdentity(_LEDGER, "revision"))
    assert concurrency.caused_by == (moved,)

    membership = _of(evolution, QueryResultMembershipChanged)
    assert [impact.scope for impact in membership] == [_ROOT, _LEDGER]
    assert [impact.caused_by for impact in membership] == [(moved,), (moved,)]


def _archive(*, writable: bool) -> Metamodel:
    note = attribute(_ARCHIVE, "note", type=STRING)
    return form_metamodel(
        source(
            Declaration(
                identity=_ARCHIVE,
                container=Table("archive"),
                persistence=(PersistenceMode.READ_WRITE if writable else PersistenceMode.READ_ONLY),
                attributes=(
                    key(_ARCHIVE),
                    note if writable else dataclasses.replace(note, read_only=True),
                ),
            )
        )
    )


def test_an_entity_write_change_dominates_the_member_impacts_it_implies() -> None:
    # Both the Entity's Persistence Mode and its member's read-only declaration
    # move, and only the Entity-level fact is reported: repeating it per member
    # would state the same withdrawal of writes several times.
    evolution = evolve(_archive(writable=True), _archive(writable=False))
    (write,) = _of(evolution, WriteCapabilityChanged)
    assert write.scope == _ARCHIVE
    assert write.earlier == WritesEnabled(EntityWriteShape.NON_TEMPORAL)
    assert write.later == WRITES_DISABLED


_MOVED_AXIS = identity("Reading")


def _moved_axis(start: str, end: str) -> Metamodel:
    """A Transaction-Time Entity whose axis names one of two candidate endpoint
    pairs, all four of which it declares.

    Axis endpoints reach a descriptor's Temporality Profile framework-fixed, so
    a moved endpoint is reachable only through the `m-metamodel` seam — which is
    the whole reason this scenario is stated here rather than in the corpus.
    """
    axis = AsOfAxisMetadata(
        TemporalDimension.TRANSACTION_TIME,
        AttributeIdentity(_MOVED_AXIS, start),
        AttributeIdentity(_MOVED_AXIS, end),
    )
    return form_metamodel(
        source(
            Declaration(
                identity=_MOVED_AXIS,
                container=Table("reading"),
                attributes=(
                    key(_MOVED_AXIS),
                    instant(_MOVED_AXIS, "openedAt"),
                    instant(_MOVED_AXIS, "closedAt"),
                    instant(_MOVED_AXIS, "seenAt"),
                    instant(_MOVED_AXIS, "goneAt"),
                ),
                as_of_axes=(axis,),
            )
        )
    )


def test_an_axis_moving_its_endpoints_moves_what_a_caller_may_supply() -> None:
    # Framework ownership is derived from axis membership rather than declared,
    # so four Attributes exchange input capability while not one of their own
    # declarations changes. The axis alteration is the only operation that could
    # have caused it, and it is what `causedBy` names.
    evolution = evolve(_moved_axis("openedAt", "closedAt"), _moved_axis("seenAt", "goneAt"))
    (altered,) = evolution.operations
    assert altered == AsOfAxisAltered(
        _MOVED_AXIS,
        TemporalDimension.TRANSACTION_TIME,
        (
            StartAttributeChanged(
                AttributeIdentity(_MOVED_AXIS, "openedAt"),
                AttributeIdentity(_MOVED_AXIS, "seenAt"),
            ),
            EndAttributeChanged(
                AttributeIdentity(_MOVED_AXIS, "closedAt"),
                AttributeIdentity(_MOVED_AXIS, "goneAt"),
            ),
        ),
    )
    writes = _of(evolution, WriteCapabilityChanged)
    assert [impact.scope for impact in writes] == [
        AttributeIdentity(_MOVED_AXIS, "closedAt"),
        AttributeIdentity(_MOVED_AXIS, "goneAt"),
        AttributeIdentity(_MOVED_AXIS, "openedAt"),
        AttributeIdentity(_MOVED_AXIS, "seenAt"),
    ]
    assert {impact.caused_by for impact in writes} == {(altered,)}
    assert [impact.earlier for impact in writes] == [
        AttributeWriteCapability.FRAMEWORK_OWNED,
        AttributeWriteCapability.CALLER_INSERT_AND_UPDATE,
        AttributeWriteCapability.FRAMEWORK_OWNED,
        AttributeWriteCapability.CALLER_INSERT_AND_UPDATE,
    ]


def _keyed_index(*, temporal: bool) -> Metamodel:
    """One Entity carrying an authored unique Index, temporal or not.

    Its derived primary-key Index gains the axis end Attribute when the profile
    does, which is the change this scenario is here to prove is NOT described.
    """
    axis = AsOfAxisMetadata(
        TemporalDimension.TRANSACTION_TIME,
        AttributeIdentity(_ARRIVAL, "txStart"),
        AttributeIdentity(_ARRIVAL, "txEnd"),
    )
    serial = attribute(_ARRIVAL, "serial", type=STRING)
    return form_metamodel(
        source(
            Declaration(
                identity=_ARRIVAL,
                container=Table("arrival"),
                attributes=(
                    key(_ARRIVAL),
                    serial,
                    *(
                        (instant(_ARRIVAL, "txStart"), instant(_ARRIVAL, "txEnd"))
                        if temporal
                        else ()
                    ),
                ),
                as_of_axes=(axis,) if temporal else (),
                indices=(
                    IndexMetadata(
                        IndexIdentity(_ARRIVAL, "arrival_serial"), (serial.identity,), unique=True
                    ),
                ),
            )
        )
    )


def test_the_derived_primary_key_index_is_neither_an_operation_nor_a_uniqueness_rule() -> None:
    # The derived Index is not independently authored: its components change with
    # the temporal profile, and that change is described by the causal As-Of Axis
    # operation rather than by an Index operation or a uniqueness impact. The
    # authored unique Index beside it is unchanged, so no rule moved either.
    evolution = evolve(_keyed_index(temporal=False), _keyed_index(temporal=True))
    assert not [
        operation
        for operation in evolution.operations
        if isinstance(operation, IndexAdded | IndexRemoved | IndexAltered)
    ]
    assert _of(evolution, UniquenessEnforcementChanged) == []


def _sealed(*, temporal: bool) -> Metamodel:
    """A READ-ONLY Entity whose two Timestamps are an axis's endpoints or are
    ordinary members, gaining an unrelated nullable member at the same time.

    Read-only is what makes the scenario reachable: the Entity write surface is
    `Disabled` at both endpoints, so the axis does not dominate its members and
    each endpoint Attribute reports the input capability it moved between. The
    unrelated addition is there to be excluded from their causes.
    """
    axis = AsOfAxisMetadata(
        TemporalDimension.TRANSACTION_TIME,
        AttributeIdentity(_ARCHIVE, "openedAt"),
        AttributeIdentity(_ARCHIVE, "closedAt"),
    )
    return form_metamodel(
        source(
            Declaration(
                identity=_ARCHIVE,
                container=Table("archive"),
                persistence=PersistenceMode.READ_ONLY,
                attributes=(
                    key(_ARCHIVE),
                    instant(_ARCHIVE, "openedAt"),
                    instant(_ARCHIVE, "closedAt"),
                    *(
                        (
                            dataclasses.replace(
                                attribute(_ARCHIVE, "memo", type=STRING), nullable=True
                            ),
                        )
                        if temporal
                        else ()
                    ),
                ),
                as_of_axes=(axis,) if temporal else (),
            )
        )
    )


def test_an_arriving_axis_claims_the_members_it_makes_its_endpoints() -> None:
    # Adding the axis leaves the Entity write surface exactly where it was, so
    # nothing dominates its members, and the two Attributes it claims move from
    # caller-supplied to framework-owned with the addition as their only cause —
    # the unrelated member arriving beside it moves nothing they report.
    evolution = evolve(_sealed(temporal=False), _sealed(temporal=True))
    (added,) = [
        operation for operation in evolution.operations if isinstance(operation, AsOfAxisAdded)
    ]
    writes = _of(evolution, WriteCapabilityChanged)
    assert [impact.scope for impact in writes] == [
        AttributeIdentity(_ARCHIVE, "closedAt"),
        AttributeIdentity(_ARCHIVE, "openedAt"),
    ]
    assert {impact.later for impact in writes} == {AttributeWriteCapability.FRAMEWORK_OWNED}
    assert {impact.caused_by for impact in writes} == {(added,)}


_PAIRED = identity("Reconciliation")


def _paired_indices(*names: tuple[str, tuple[str, ...]]) -> Metamodel:
    """A `Reconciliation` carrying one unique Index per named component tuple."""
    members = tuple(attribute(_PAIRED, name, type=STRING) for name in ("left", "right", "note"))
    return form_metamodel(
        source(
            Declaration(
                identity=_PAIRED,
                container=Table("reconciliation"),
                attributes=(key(_PAIRED), *members),
                indices=tuple(
                    IndexMetadata(
                        IndexIdentity(_PAIRED, name),
                        tuple(AttributeIdentity(_PAIRED, component) for component in components),
                        unique=True,
                    )
                    for name, components in names
                ),
            )
        )
    )


def test_two_equivalent_indices_trading_places_cause_nothing_they_did_not_move() -> None:
    # A uniqueness rule is an unordered Attribute set, so an Index removed and an
    # equivalent one added enforce the same rule throughout: the impact beside
    # them is caused by the Index that carries the rule the two sets differ by,
    # and by that one alone.
    evolution = evolve(
        _paired_indices(("by_pair", ("left", "right"))),
        _paired_indices(("by_swap", ("right", "left")), ("by_note", ("note",))),
    )
    (enforcement,) = _of(evolution, UniquenessEnforcementChanged)
    assert enforcement.caused_by == (IndexAdded(IndexIdentity(_PAIRED, "by_note")),)


def _subtree(*, under: EntityIdentity) -> Metamodel:
    """Two roots, one of them Transaction-Time, with an ABSTRACT position — and
    the concrete Entity below it — hanging from ``under``."""
    declarations = (
        Declaration(
            identity=_ROOT,
            container=Table("instrument"),
            attributes=(key(_ROOT),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_LEDGER,
            container=Table("ledger"),
            attributes=(key(_LEDGER), instant(_LEDGER, "txStart"), instant(_LEDGER, "txEnd")),
            as_of_axes=(
                AsOfAxisMetadata(
                    TemporalDimension.TRANSACTION_TIME,
                    AttributeIdentity(_LEDGER, "txStart"),
                    AttributeIdentity(_LEDGER, "txEnd"),
                ),
            ),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_STOCK,
            attributes=(attribute(_STOCK, "ticker", type=STRING),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "STOCK"),
        ),
        Declaration(
            identity=_ENTRY,
            attributes=(attribute(_ENTRY, "amount"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_LEDGER), "ENTRY"),
        ),
        Declaration(
            identity=_NOTE,
            inheritance=AbstractSubtype(ExactEntityReference(under)),
        ),
        Declaration(
            identity=_BOND,
            attributes=(attribute(_BOND, "coupon"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_NOTE), "BOND"),
        ),
    )
    return form_metamodel(source(*declarations))


def test_an_abstract_position_moving_is_the_cause_above_and_below_it() -> None:
    # The moved position is abstract, so it denotes no rows and appears in no
    # concrete set, and the Entity below it declares no inheritance change of its
    # own: nothing names the two positions the move actually carried. Every
    # impact the one alteration causes — the roots it left and joined, the
    # position itself, and the concrete Entity beneath it — names that operation,
    # and none of them is left without a cause. The moved position takes the
    # Transaction-Time shape of the family it joins, but only the concrete Entity
    # beneath it reports a write capability: an abstract subtype is a read
    # position under either root.
    evolution = evolve(_subtree(under=_ROOT), _subtree(under=_LEDGER))
    (moved,) = [
        operation for operation in evolution.operations if isinstance(operation, EntityAltered)
    ]
    assert {(type(impact).__name__, impact.scope) for impact in evolution.behavioral_impacts} == {
        ("ConcurrencyControlChanged", _BOND),
        ("ConcurrencyControlChanged", _NOTE),
        ("QueryResultMembershipChanged", _BOND),
        ("QueryResultMembershipChanged", _LEDGER),
        ("QueryResultMembershipChanged", _NOTE),
        ("QueryResultMembershipChanged", _ROOT),
        ("WriteCapabilityChanged", _BOND),
    }
    assert {impact.caused_by for impact in evolution.behavioral_impacts} == {(moved,)}


def _tagged(tag: str, *, extended: bool) -> Metamodel:
    """A table-per-hierarchy family whose concrete `Bond` carries ``tag``,
    optionally extended by a second concrete position."""
    declarations = [
        Declaration(
            identity=_ROOT,
            container=Table("instrument"),
            attributes=(key(_ROOT),),
            inheritance=AbstractRoot(TablePerHierarchy("kind")),
        ),
        Declaration(
            identity=_BOND,
            attributes=(attribute(_BOND, "coupon"),),
            inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), tag),
        ),
    ]
    if extended:
        declarations.append(
            Declaration(
                identity=_STOCK,
                attributes=(attribute(_STOCK, "ticker", type=STRING),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "STOCK"),
            )
        )
    return form_metamodel(source(*declarations))


def test_a_re_tagged_position_moves_nothing_the_family_denotes() -> None:
    # A tag value is an inheritance change that leaves every position exactly
    # where it was: the root denotes a different concrete set here, but the
    # arriving subtype is the whole of why, and the re-tagged one is named by
    # nothing.
    evolution = evolve(_tagged("BOND", extended=False), _tagged("SENIOR", extended=True))
    (membership,) = _of(evolution, QueryResultMembershipChanged)
    assert membership.scope == _ROOT
    assert membership.caused_by == (ConcreteSubtypeAdded(_STOCK),)


def _closing(*, sealed: bool) -> Metamodel:
    """An `Archive` that withdraws its writes and gains a Transaction-Time axis
    over two Timestamps it already declared, in one evolution."""
    axis = AsOfAxisMetadata(
        TemporalDimension.TRANSACTION_TIME,
        AttributeIdentity(_ARCHIVE, "openedAt"),
        AttributeIdentity(_ARCHIVE, "closedAt"),
    )
    return form_metamodel(
        source(
            Declaration(
                identity=_ARCHIVE,
                container=Table("archive"),
                persistence=(PersistenceMode.READ_ONLY if sealed else PersistenceMode.READ_WRITE),
                attributes=(
                    key(_ARCHIVE),
                    instant(_ARCHIVE, "openedAt"),
                    instant(_ARCHIVE, "closedAt"),
                ),
                as_of_axes=(axis,) if sealed else (),
            )
        )
    )


def test_an_axis_behind_a_withdrawn_write_surface_is_no_cause_of_it() -> None:
    # A surface admitting no write carries no temporal shape, so the axis
    # arriving beside the withdrawal moved nothing the impact reports: the
    # Persistence Mode is its whole cause.
    evolution = evolve(_closing(sealed=False), _closing(sealed=True))
    (added,) = [
        operation for operation in evolution.operations if isinstance(operation, AsOfAxisAdded)
    ]
    (write,) = _of(evolution, WriteCapabilityChanged)
    assert (write.scope, write.later) == (_ARCHIVE, WRITES_DISABLED)
    assert added not in write.caused_by
    assert [type(operation) for operation in write.caused_by] == [EntityAltered]


def _write_handle_and_axis(*, concrete: bool, dated: bool) -> Metamodel:
    """An `Instrument` family whose `Note` holds the concrete-subtype role or the
    abstract one, gaining a Transaction-Time axis over Instants it already
    declared in the same evolution."""
    return form_metamodel(
        source(
            Declaration(
                identity=_ROOT,
                container=Table("instrument"),
                attributes=(key(_ROOT), instant(_ROOT, "txStart"), instant(_ROOT, "txEnd")),
                as_of_axes=(_TRANSACTION_TIME,) if dated else (),
                inheritance=AbstractRoot(TablePerHierarchy("kind")),
            ),
            Declaration(
                identity=_BOND,
                attributes=(attribute(_BOND, "coupon"),),
                inheritance=ConcreteSubtype(ExactEntityReference(_ROOT), "BOND"),
            ),
            Declaration(
                identity=_NOTE,
                inheritance=(
                    ConcreteSubtype(ExactEntityReference(_ROOT), "NOTE")
                    if concrete
                    else AbstractSubtype(ExactEntityReference(_ROOT))
                ),
            ),
        )
    )


def test_an_axis_behind_a_surrendered_write_handle_is_no_cause_of_it() -> None:
    # A position that gives up the concrete-subtype role stops being a write
    # handle, so its later surface admits no write and carries no temporal shape:
    # the role change is the whole cause, and the axis arriving beside it moved
    # nothing this impact reports. The concrete sibling, whose handle survives,
    # names that same axis as the whole cause of its own shape moving.
    evolution = evolve(
        _write_handle_and_axis(concrete=True, dated=False),
        _write_handle_and_axis(concrete=False, dated=True),
    )
    (added,) = [
        operation for operation in evolution.operations if isinstance(operation, AsOfAxisAdded)
    ]
    (altered,) = [
        operation for operation in evolution.operations if isinstance(operation, EntityAltered)
    ]
    (note,) = [impact for impact in _of(evolution, WriteCapabilityChanged) if impact.scope == _NOTE]
    assert (note.earlier, note.later) == (
        WritesEnabled(EntityWriteShape.NON_TEMPORAL),
        WRITES_DISABLED,
    )
    assert note.caused_by == (altered,)
    (bond,) = [impact for impact in _of(evolution, WriteCapabilityChanged) if impact.scope == _BOND]
    assert bond.later == WritesEnabled(EntityWriteShape.TRANSACTION_TIME_ONLY)
    assert bond.caused_by == (added,)


def _admitted(*, temporal: bool) -> Metamodel:
    """A read-only `Archive` whose `openedAt` stops admitting absence exactly
    when the axis that claims it arrives."""
    axis = AsOfAxisMetadata(
        TemporalDimension.TRANSACTION_TIME,
        AttributeIdentity(_ARCHIVE, "openedAt"),
        AttributeIdentity(_ARCHIVE, "closedAt"),
    )
    opened = instant(_ARCHIVE, "openedAt")
    return form_metamodel(
        source(
            Declaration(
                identity=_ARCHIVE,
                container=Table("archive"),
                persistence=PersistenceMode.READ_ONLY,
                attributes=(
                    key(_ARCHIVE),
                    opened if temporal else dataclasses.replace(opened, nullable=True),
                    instant(_ARCHIVE, "closedAt"),
                ),
                as_of_axes=(axis,) if temporal else (),
            )
        )
    )


def test_an_alteration_that_moves_no_ownership_is_no_cause_of_a_write_impact() -> None:
    # Caller ownership follows key membership, the read-only fact, and optimistic
    # locking; this Attribute's own alteration moves none of them. The axis
    # claiming it as an endpoint is what withdrew the caller's input, and the
    # nullability delta stays where it belongs — on the value domain.
    evolution = evolve(_admitted(temporal=False), _admitted(temporal=True))
    (added,) = [
        operation for operation in evolution.operations if isinstance(operation, AsOfAxisAdded)
    ]
    (altered,) = [
        operation for operation in evolution.operations if isinstance(operation, AttributeAltered)
    ]
    opened = AttributeIdentity(_ARCHIVE, "openedAt")
    (write,) = [
        impact for impact in _of(evolution, WriteCapabilityChanged) if impact.scope == opened
    ]
    assert write.later == AttributeWriteCapability.FRAMEWORK_OWNED
    assert write.caused_by == (added,)
    (admissibility,) = _of(evolution, ValueAdmissibilityChanged)
    assert (admissibility.scope, admissibility.caused_by) == (opened, (altered,))
