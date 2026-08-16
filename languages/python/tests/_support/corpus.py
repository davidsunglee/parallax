"""Case documents and the corpus-grading comparators.

The run sweep and the API-suite story lane grade against the same case oracles,
so the comparators are surface-neutral rather than owned by either.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from parallax.core.entity import Entity
    from parallax.core.inheritance import InheritanceEntityView
    from parallax.core.metamodel import (
        EntityIdentity,
        Metamodel,
        NestedValueObjectMetadata,
        ValueObjectMetadata,
    )


def case_document(case: Any) -> dict[str, Any]:
    """A case's raw YAML document as a plain ``dict`` (test-side typed accessor)."""
    return cast("dict[str, Any]", dict(case.document))


def case_fixtures(case: Any) -> dict[str, Any]:
    """The fixtures the case's lifecycle loads before its action (m-case-format).

    A writeSequence case starts from an EMPTY schema and builds its own state
    unless it opts in with `given.fixtures: true`; every other shape starts from
    the model's default fixtures (a case that injects nothing omits `given`).
    """
    doc = case_document(case)
    given = cast("dict[str, Any]", doc.get("given") or {})
    if case.shape == "writeSequence" and not given.get("fixtures"):
        return {}
    from parallax.conformance import provision

    return provision.load_fixtures(str(doc["model"]))


def _wire_row(row: dict[str, Any]) -> dict[str, Any]:
    # Observed rows arrive already wire-rendered; authored expectation rows are
    # normalized through the same m-db-port boundary so dates / uuids / bytes are
    # compared in one canonical form.
    from parallax.conformance import engine

    return {key: engine.wire_value(value) for key, value in row.items()}


def _to_decimal(value: object) -> object:
    """Coerce a numeric (or a wire-rendered numeric string) to an exact ``Decimal``.

    The corpus grades numerics as exact Decimals (m-case-format), so a ``decimal``
    money column matches to the cent regardless of scale. A wire-rendered decimal
    arrives as a numeric *string* — its canonical wire form is the exact string, not
    a float — so a numeric-looking string is parsed too; a non-numeric string / date
    / uuid raises and passes through for exact ``==``.
    """
    from decimal import Decimal, InvalidOperation

    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    return value


def _to_instant(value: object) -> object:
    """Coerce an ISO-8601 instant spelling to the instant it names.

    `m-case-format` admits both spellings of one UTC instant — the ``Z`` suffix a
    canonical Wire Value carries (`m-wire`) and the ``+00:00`` offset the corpus
    authors — so a residual difference between two strings that name the same
    moment is a spelling difference, not a value one. Anything that is not an
    instant spelling passes through for exact ``==``.
    """
    import datetime as dt

    if not isinstance(value, str):
        return value
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed if parsed.tzinfo is not None else value


def _scalar_equal(observed: object, expected: object) -> bool:
    """Exact wire equality, with exact-Decimal and instant fallbacks.

    Exact ``==`` decides every string / date / uuid / bytes / bool value (so this
    never loosens a comparison that already holds); only a residual difference in
    an admitted second spelling reconciles — the wire-rendered ``decimal`` string
    ``"99.99"`` against the authored number ``99.99`` in Decimal space, and the
    canonical ``...Z`` instant against the authored ``...+00:00`` one as the
    moment both name. ``bool`` is never numeric (``True`` never equals ``1``).
    """
    from decimal import Decimal

    if observed == expected:
        return True
    if isinstance(observed, bool) or isinstance(expected, bool):
        return False
    left, right = _to_decimal(observed), _to_decimal(expected)
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        return left == right
    return _to_instant(observed) == _to_instant(expected)


def _row_equal(observed: dict[str, Any], expected: dict[str, Any]) -> bool:
    return observed.keys() == expected.keys() and all(
        _scalar_equal(observed[key], expected[key]) for key in observed
    )


def compare_binds(observed: Sequence[object], expected: Sequence[object]) -> None:
    """Order-SENSITIVE positional bind comparison with the same exact-Decimal
    fallback ``compare_rows`` uses (m-case-format): an authored golden literal
    (``5.00``, a plain YAML float) and a real ``decimal``-typed bind
    (``Decimal("5.00")``, e.g. an idiomatic entity instance's own field value)
    reconcile in Decimal space; a value-object document write's own bind (a
    ``JsonDocument`` carrier, `m-db-port`) unwraps to its underlying JSON
    document before comparing, so it reconciles against the golden's plain
    dict/list literal exactly like `parallax.conformance.engine._json_bind`'s
    own emission-wire rendering; everything else is exact wire equality.
    """
    obs = [_wire_value(value) for value in observed]
    exp = [_wire_value(value) for value in expected]
    assert len(obs) == len(exp), f"bind count: observed {obs!r} != expected {exp!r}"
    for index, (left, right) in enumerate(zip(obs, exp, strict=True)):
        assert _scalar_equal(left, right), (index, left, right)


def _wire_value(value: object) -> object:
    from parallax.conformance import engine
    from parallax.core.db_port import JsonDocument

    if isinstance(value, JsonDocument):
        return value.value
    return engine.wire_value(value)


def compare_rows(observed: list[dict[str, Any]], expected: list[dict[str, Any]]) -> None:
    """Order-insensitive multiset comparison (greedy — result sets are tiny)."""
    obs = [_wire_row(row) for row in observed]
    remaining = [_wire_row(row) for row in expected]
    assert len(obs) == len(remaining), f"row count: observed {obs!r} != expected {remaining!r}"
    for row in obs:
        for index, candidate in enumerate(remaining):
            if _row_equal(row, candidate):
                del remaining[index]
                break
        else:
            raise AssertionError(f"observed row unmatched: {row!r}\n  expected pool: {remaining!r}")


def instance_row(instance: Entity, *, family_variant: bool = False) -> dict[str, Any]:
    """Render one materialized entity instance's OWN scalar/value-object
    members to a PHYSICAL-COLUMN-keyed row — the same key convention
    ``then.rows`` / ``expectRows`` use (`m-case-format` "Triple equivalence":
    a case's expected row is asserted against the golden SQL's OWN projected
    column names, e.g. ``ordered_on``, never the canonical camelCase wire
    name ``orderedOn`` an Entity Row Codec row is keyed by).
    ``family_variant=True``
    additionally reports ``familyVariant`` as ``type(instance).__name__`` —
    the API-suite's own observation of polymorphism (`python.md` §4: "every
    materialized node is an instance of its concrete entity class, so the
    corpus's `familyVariant` is observable as `type(node)`"), needed only when
    grading a case whose oracle projects the raw tag column for an
    abstract-root read.
    """
    from parallax.core.entity._entity import wire_names_of

    names = wire_names_of(type(instance))
    column_by_py = {py_name: column for column, py_name in names.column_to_py.items()}
    row = {column_by_py[py_name]: getattr(instance, py_name) for py_name in names.py_to_name}
    if family_variant:
        row["familyVariant"] = type(instance).__name__
    return row


def instance_graph_node(instance: Entity, *, family_variant: bool = False) -> dict[str, Any]:
    """Render one materialized entity instance's OWN scalar/value-object
    members to a DECLARED-MEMBER-keyed node — the key convention
    ``then.graph`` / ``then.graphs`` use (`m-case-format` "Graph keys": a graph
    leaf is keyed by the name the model declares, e.g. ``orderedOn``, never the
    physical column ``ordered_on`` a `then.rows` oracle spells).
    ``family_variant=True`` additionally reports ``familyVariant`` as
    ``type(instance).__name__`` — the API-suite's own observation of
    polymorphism (`python.md` §4: "every materialized node is an instance of its
    concrete entity class, so the corpus's `familyVariant` is observable as
    `type(node)`").
    """
    from parallax.core.entity._entity import wire_names_of

    names = wire_names_of(type(instance))
    node = {name: getattr(instance, py_name) for py_name, name in names.py_to_name.items()}
    if family_variant:
        node["familyVariant"] = type(instance).__name__
    return node


# --------------------------------------------------------------------------- #
# Graph comparison (m-case-format `then.graph` / `then.graphs` leaves): a      #
# recursive structural comparison over nested dicts/lists, sharing the same   #
# exact-Decimal / wire-normalized scalar rules `compare_rows` uses.           #
# --------------------------------------------------------------------------- #
def wire_value_deep(value: object) -> object:
    from parallax.conformance import engine

    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: wire_value_deep(v) for key, v in mapping.items()}
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [wire_value_deep(v) for v in items]
    return engine.wire_value(value)


@dataclass(frozen=True, slots=True)
class CollectionKinds:
    """The model a graph observation is graded against, and where it sits in it.

    `m-case-format` ("Graph comparison distinguishes collection kinds") compares a
    root result set and a relationship collection as MULTISETS and a Value Object
    `many` occurrence POSITIONALLY, because that occurrence's element order is
    semantic (`m-value-object`) and its duplicates stay distinct. Both are arrays
    of objects in an assembled graph, so nothing in the value tells them apart:
    only the declaration at the key does, and comparison walks the model beside
    the value.

    ``entity`` names the Entity whose own node the observation IS, for a lane that
    grades one node at a time; absent, the observation is the root-keyed whole
    graph, whose keys name the read's own result Entities.
    """

    model: Metamodel
    entity: str | None = None


type _Level = _Roots | _Node | _Occurrence
"""What one graph position's keys mean — the model position a mapping occupies."""


@dataclass(frozen=True, slots=True)
class _Key:
    """How the value under one key compares, and what its own keys mean.

    ``ordered`` is absent where the model declares no collection at the key, which
    is what turns a list arriving there into a named grading gap rather than a
    silently chosen rule.
    """

    ordered: bool | None
    level: _Level | None


_UNDECLARED: Final = _Key(None, None)


@dataclass(frozen=True, slots=True)
class _Roots:
    """A root-keyed graph: each key one Entity's own name, each value its result set."""

    model: Metamodel

    def key(self, name: str) -> _Key:
        level = _entity_level(self.model, name)
        return _UNDECLARED if level is None else _Key(False, level)


@dataclass(frozen=True, slots=True)
class _Node:
    """One Entity node: its declared members, plus the relationship views a deep
    fetch keys onto it — the plain relationship name or the narrowed
    ``<rel>[<Concrete>,…]`` derived key (`m-case-format`)."""

    model: Metamodel
    view: InheritanceEntityView

    def key(self, name: str) -> _Key:
        occurrence = self._occurrence(name)
        if occurrence is not None:
            return _occurrence_key(self.model, occurrence)
        related = self._related(name)
        return _UNDECLARED if related is None else _Key(False, related)

    def _occurrence(self, name: str) -> ValueObjectMetadata | None:
        """The occurrence ``name`` denotes, family-wide: an abstract position's node
        is a concrete variant, so the projection superset answers where the
        position's own applicable set cannot."""
        own = self.view.applicable_value_object(name)
        if own is not None:
            return own
        return next(
            (
                occurrence
                for occurrence in self.view.superset_value_objects
                if occurrence.identity.path[-1] == name
            ),
            None,
        )

    def _related(self, name: str) -> _Node | None:
        """The node level one relationship view key reaches, broad or narrowed."""
        from parallax.core.relationship import view as relationship_view

        declared = self.view.applicable_relationship(name.split("[", 1)[0])
        if declared is None:
            return None
        direction = relationship_view(self.model).relationship(declared.identity)
        return None if direction is None else _node_level(self.model, direction.join.target.entity)


@dataclass(frozen=True, slots=True)
class _Occurrence:
    """One Value Object occurrence's document: its leaves and nested occurrences."""

    model: Metamodel
    declared: ValueObjectMetadata | NestedValueObjectMetadata

    def key(self, name: str) -> _Key:
        nested = self.declared.value_object(name)
        return _UNDECLARED if nested is None else _occurrence_key(self.model, nested)


def _occurrence_key(
    model: Metamodel, declared: ValueObjectMetadata | NestedValueObjectMetadata
) -> _Key:
    """One occurrence key: a `many` holds the ordered element documents the stored
    order is, a `one` a single document and never a collection."""
    from parallax.core.metamodel import Multiplicity

    ordered = True if declared.multiplicity is Multiplicity.MANY else None
    return _Key(ordered, _Occurrence(model, declared))


def _entity_level(model: Metamodel, name: str) -> _Node | None:
    """The node level a graph key's Entity spelling denotes, absent for a name the
    model declares no Entity under."""
    from parallax.core.metamodel import entity_by_name

    entity = entity_by_name(model, name)
    return None if entity is None else _node_level(model, entity.identity)


def _node_level(model: Metamodel, identity: EntityIdentity) -> _Node | None:
    """One Entity's node level, absent only for an Identity the model lacks."""
    from parallax.core.inheritance import view as inheritance_view

    view = inheritance_view(model).entity(identity)
    return None if view is None else _Node(model, view)


def _member_key(key: _Key, name: str) -> _Key:
    return _UNDECLARED if key.level is None else key.level.key(name)


def _element_key(key: _Key) -> _Key:
    """One element of a graph collection: the level its own key names, carrying no
    collection of its own."""
    return _Key(None, key.level)


def _values_equal(observed: object, expected: object, key: _Key, path: str) -> bool:
    if isinstance(expected, Mapping):
        expected_map = cast("Mapping[str, object]", expected)
        if not isinstance(observed, Mapping):
            return False
        observed_map = cast("Mapping[str, object]", observed)
        return set(observed_map) == set(expected_map) and all(
            _values_equal(
                observed_map[name], expected_map[name], _member_key(key, name), f"{path}.{name}"
            )
            for name in expected_map
        )
    if isinstance(expected, list):
        expected_items = cast("list[object]", expected)
        if not isinstance(observed, list):
            return False
        observed_items = cast("list[object]", observed)
        if len(observed_items) != len(expected_items):
            return False
        if key.ordered is None:
            raise AssertionError(
                f"{path}: the model declares no collection at this position, so neither "
                "graph comparison rule (m-case-format) decides its elements"
            )
        element = _element_key(key)
        if key.ordered:
            return all(
                _values_equal(item, candidate, element, f"{path}[{index}]")
                for index, (item, candidate) in enumerate(
                    zip(observed_items, expected_items, strict=True)
                )
            )
        remaining = list(expected_items)
        for item in observed_items:
            for index, candidate in enumerate(remaining):
                if _values_equal(item, candidate, element, path):
                    del remaining[index]
                    break
            else:
                return False
        return True
    return _scalar_equal(observed, expected)


def _root_key(kinds: CollectionKinds) -> _Key:
    if kinds.entity is None:
        return _Key(None, _Roots(kinds.model))
    level = _entity_level(kinds.model, kinds.entity)
    assert level is not None, f"{kinds.entity!r} names no Entity the graded model declares"
    return _Key(None, level)


def compare_graph(
    observed: Mapping[str, Any], expected: Mapping[str, Any], kinds: CollectionKinds
) -> None:
    """Assert one assembled `then.graph` / `then.graphs` leaf equals ``expected``
    (m-case-format), both sides normalized through the same wire-value rules
    `compare_rows` uses for a flat row, and every collection compared by the kind
    ``kinds`` reads off the model."""
    observed_wire = wire_value_deep(dict(observed))
    expected_wire = wire_value_deep(dict(expected))
    assert _values_equal(observed_wire, expected_wire, _root_key(kinds), kinds.entity or "graph"), (
        f"graph mismatch:\n  observed: {observed_wire!r}\n  expected: {expected_wire!r}"
    )


def compare_stored_data_issues(observed: object, expected: object) -> None:
    """Assert a read's classified positions equal what the case authored.

    Both sides are compared as authored — an ordered list of records, each
    carrying its ordinal, whether hydration completed, and its own diagnosis set.
    A conforming read publishes none and a case that expects none authors none,
    so the absent-versus-empty distinction never arises: the harness compares the
    two absences directly.
    """
    assert observed == expected, (
        f"stored-data classification mismatch:\n  observed: {observed!r}\n  expected: {expected!r}"
    )


_CALL_PATH = re.compile(r"/calls/\d+$")


def _unasserted_licence(path: str) -> frozenset[str]:
    """The observation keys the oracle at ``path`` may legitimately leave unsaid.

    The list is closed and comes from `m-case-format`: a call's `statement` index
    is omitted on a lane that authors no golden SQL, and a failure's `code` is an
    optional implementation-level value. Nothing else is a don't-care — the
    oracle states attempt, trace, call, completion, and (for a rolled-back
    attempt) failure structure, so a key the observation carries and the oracle
    never mentions is an UNASSERTED claim rather than a permitted omission.
    """
    if path.endswith("/failure"):
        return frozenset({"code"})
    if _CALL_PATH.search(path):
        return frozenset({"statement"})
    return frozenset()


def _execution_mismatch(observed: object, expected: object, path: str) -> str | None:
    """The first place ``observed`` fails to satisfy the ``expected`` oracle, or
    ``None``.

    Every authored key must match exactly, a sequence must match element for
    element with no length slack — the ORDER traces reached the database in is
    the assertion — and an observed key the oracle never states is a mismatch
    unless :func:`_unasserted_licence` names it. That last rule is what stops a
    run from passing while it reports, say, a failure on an attempt the oracle
    describes as carrying none.
    """
    if isinstance(expected, Mapping):
        if not isinstance(observed, Mapping):
            return f"{path}: expected an object, observed {observed!r}"
        observed_map = cast("Mapping[str, Any]", observed)
        expected_map = cast("Mapping[str, Any]", expected)
        unasserted = sorted(set(observed_map) - set(expected_map) - _unasserted_licence(path))
        if unasserted:
            return (
                f"{path}: the observed provenance carries {', '.join(unasserted)}, "
                "which the oracle does not state"
            )
        for key, value in expected_map.items():
            if key not in observed_map:
                return f"{path}/{key}: absent from the observed provenance"
            mismatch = _execution_mismatch(observed_map[key], value, f"{path}/{key}")
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(expected, list):
        expected_list = cast("list[Any]", expected)
        if not isinstance(observed, list):
            return f"{path}: expected an array, observed {observed!r}"
        observed_list = cast("list[Any]", observed)
        if len(observed_list) != len(expected_list):
            return f"{path}: expected {len(expected_list)} entr(ies), observed {len(observed_list)}"
        for index, value in enumerate(expected_list):
            mismatch = _execution_mismatch(observed_list[index], value, f"{path}/{index}")
            if mismatch is not None:
                return mismatch
        return None
    if observed != expected:
        return f"{path}: expected {expected!r}, observed {observed!r}"
    return None


def compare_execution(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """Assert an `execution` observation satisfies the case's `then.execution`
    oracle (m-execution-log)."""
    mismatch = _execution_mismatch(observed, expected, "execution")
    assert mismatch is None, (
        f"execution provenance mismatch — {mismatch}\n"
        f"  observed: {observed!r}\n  expected: {expected!r}"
    )
