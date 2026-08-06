"""Case documents and the corpus-grading comparators.

The run sweep and the API-suite story lane grade against the same case oracles,
so the comparators are surface-neutral rather than owned by either.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from parallax.core.entity import Entity


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


def _scalar_equal(observed: object, expected: object) -> bool:
    """Exact wire equality, with an exact-Decimal fallback for numerics.

    Exact ``==`` decides every string / date / uuid / bytes / bool value (so this
    never loosens a comparison that already holds); only a residual numeric
    difference — the wire-rendered ``decimal`` string ``"99.99"`` against the
    authored number ``99.99`` — reconciles in Decimal space. ``bool`` is never
    numeric (``True`` never equals ``1``).
    """
    from decimal import Decimal

    if observed == expected:
        return True
    if isinstance(observed, bool) or isinstance(expected, bool):
        return False
    left, right = _to_decimal(observed), _to_decimal(expected)
    return isinstance(left, Decimal) and isinstance(right, Decimal) and left == right


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
    name ``orderedOn`` ``canonical_row`` renders). ``family_variant=True``
    additionally reports ``familyVariant`` as ``type(instance).__name__`` —
    the API-suite's own observation of polymorphism (`python.md` §4: "every
    materialized node is an instance of its concrete entity class, so the
    corpus's `familyVariant` is observable as `type(node)`"), needed only when
    grading a case whose oracle projects the raw tag column for an
    abstract-root read.
    """
    from parallax.core.entity import wire_names_of

    names = wire_names_of(type(instance))
    column_by_py = {py_name: column for column, py_name in names.column_to_py.items()}
    row = {column_by_py[py_name]: getattr(instance, py_name) for py_name in names.py_to_name}
    if family_variant:
        row["familyVariant"] = type(instance).__name__
    return row


# --------------------------------------------------------------------------- #
# Graph comparison (m-case-format `then.graph` / `then.graphs` leaves): a      #
# recursive structural comparison over nested dicts/lists, sharing the same   #
# exact-Decimal / wire-normalized scalar rules `compare_rows` uses.           #
# --------------------------------------------------------------------------- #
def value_object_projection(value: Any) -> dict[str, Any] | None:
    """One materialized Value Object as the DECLARED projection a `then.graph`
    leaf grades: EVERY declared member, canonically named, valued as the carrier
    reads it, recursively. A member the stored document omitted collapses to
    `None` / `()` exactly as one it stored as JSON null does — the absence
    collapse `m-op-algebra` fixes and `m-value-object-023` states in its own
    words ("every declared member is present").

    Deliberately not `to_document`: canonical document serialization is
    presence-filtered, so it omits a member storage never held. The carrier keeps
    that distinction — it is what lets an edited copy author an explicit null
    over an omission — and `then.graph` deliberately does not grade it. Values
    stay MANAGED here, exactly as the wire-level engine's own graph rendering
    leaves them, so both sides normalize through one wire rule.
    """
    from parallax.core.entity import ValueObject, shape_of

    if value is None:
        return None
    declared = shape_of(cast("type[ValueObject]", type(value)))
    projected: dict[str, Any] = {}
    for py_name, canonical in declared.py_to_name.items():
        member: Any = getattr(value, py_name)
        if py_name in declared.many_py:
            projected[canonical] = [value_object_projection(element) for element in member]
        elif isinstance(member, ValueObject):
            projected[canonical] = value_object_projection(member)
        else:
            projected[canonical] = member
    return projected


def wire_value_deep(value: object) -> object:
    from parallax.conformance import engine

    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: wire_value_deep(v) for key, v in mapping.items()}
    if isinstance(value, list):
        items = cast("list[object]", value)
        return [wire_value_deep(v) for v in items]
    return engine.wire_value(value)


def _values_equal(observed: object, expected: object) -> bool:
    if isinstance(expected, Mapping):
        expected_map = cast("Mapping[str, object]", expected)
        if not isinstance(observed, Mapping):
            return False
        observed_map = cast("Mapping[str, object]", observed)
        return set(observed_map) == set(expected_map) and all(
            _values_equal(observed_map[key], expected_map[key]) for key in expected_map
        )
    if isinstance(expected, list):
        expected_items = cast("list[object]", expected)
        if not isinstance(observed, list):
            return False
        observed_items = cast("list[object]", observed)
        if len(observed_items) != len(expected_items):
            return False
        if all(_values_equal(o, e) for o, e in zip(observed_items, expected_items, strict=True)):
            return True
        # A to-many value-object member's element order is UNSPECIFIED
        # (m-value-object); fall back to order-insensitive multiset matching —
        # a declared relationship `orderBy`'s exact order already matched above.
        remaining = list(expected_items)
        for item in observed_items:
            for index, candidate in enumerate(remaining):
                if _values_equal(item, candidate):
                    del remaining[index]
                    break
            else:
                return False
        return True
    return _scalar_equal(observed, expected)


def compare_graph(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    """Assert one assembled `then.graph` / `then.graphs` leaf equals ``expected``
    (m-case-format), both sides normalized through the same wire-value rules
    `compare_rows` uses for a flat row."""
    observed_wire = wire_value_deep(dict(observed))
    expected_wire = wire_value_deep(dict(expected))
    assert _values_equal(observed_wire, expected_wire), (
        f"graph mismatch:\n  observed: {observed_wire!r}\n  expected: {expected_wire!r}"
    )
