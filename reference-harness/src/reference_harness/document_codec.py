"""The portable document encoding, decoded and encoded independently (m-document-codec).

The harness's own reading of the module contract, written against raw descriptor
dictionaries rather than compiled Metadata — a second implementation of one normative
table, which is the whole point of the two-oracle design. Nothing here is shared with
the Python target: a golden document that both implementations produce is evidence,
and one only this module produces is a finding.

Three things live here rather than in three consumers:

* :func:`encode_document` — one Value Object occurrence's neutral write input as the
  document a conforming writer must bind, so a golden bind can be graded against the
  case's own ``rows`` instead of being trusted — and :func:`decode_leaf`, its per-leaf
  inverse, which is how a member a Relational Document Layout moved inside the shared
  Structured Column reaches a result row spelled as a Column of its own would spell it.
* :func:`comparison_text` and :func:`encode_candidate` — the two literal forms SQL
  lowering takes from this module, for the text-compared half of the comparison split
  and for MariaDB's containment candidate.
* :func:`is_document` and :func:`decode_stored` — the provider-facing pair. A portable
  document is recognized once, on the way to a driver's structured-document wrapper,
  and parsed once on the way back, rather than at each provider and again in the case
  runner.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import json
import re
import uuid as _uuid
from typing import Any

__all__ = [
    "DocumentEncodingError",
    "comparison_text",
    "decode_leaf",
    "decode_stored",
    "encode_candidate",
    "encode_document",
    "encode_leaf",
    "is_document",
    "is_text_compared",
]

# The declared types whose document form is a JSON string AND whose SQL comparison is
# of the extracted text (m-dialect). `decimal(p, s)` is a JSON string too and is
# deliberately absent: it casts with the numeric family, because its integer part has
# no fixed width, so `10.00` sorts below `9.00` as text.
_TEXT_COMPARED = frozenset({"string", "bytes", "date", "time", "timestamp", "uuid"})

# The declared types whose document spelling is already the value a Column of the
# same type reads back as here, so decoding one out of a document is the identity.
_IDENTITY_DECODED = frozenset(
    {"boolean", "int32", "int64", "float32", "float64", "string", "bytes", "date", "time", "uuid"}
)

_DECIMAL_TYPE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$")


class DocumentEncodingError(Exception):
    """A value has no document spelling under the type its member declares."""


def is_text_compared(type_spelling: str) -> bool:
    """Whether a document-resident member of this declared type compares as extracted
    text rather than through a dialect cast (m-dialect)."""
    return type_spelling in _TEXT_COMPARED


def is_document(value: Any) -> bool:
    """Whether ``value`` is a portable document rather than a scalar bind.

    A document crosses the bind seam as itself and each provider hands it to its own
    driver's structured-document wrapper; a JSON *string* argument a dialect spells —
    the array guard's ``[]`` — stays a string and is not one of these.
    """
    return isinstance(value, (dict, list))


def decode_stored(raw: Any) -> Any:
    """A structured-document column value read back from a driver, as a document.

    Postgres returns its ``jsonb`` column already parsed; MariaDB returns its ``json``
    column as the raw JSON text. Both collapse to the same portable document here, so
    every consumer above the driver is dialect-agnostic. A SQL ``NULL`` column stays
    ``None``.
    """
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        raw = bytes(raw).decode()
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


def encode_leaf(type_spelling: str, value: Any) -> Any:
    """``value``'s one document spelling under the declared type.

    The domain is the case corpus's own wire literals — the spelling a neutral value
    rides in YAML — because that is what a case authors and what a conforming writer
    receives. Every type has exactly one document form, so two writers of one value
    produce one document.
    """
    if value is None:
        return None
    decimal_type = _DECIMAL_TYPE.match(type_spelling)
    if decimal_type is not None:
        return _exact_decimal(value, int(decimal_type.group(2)))
    if type_spelling == "bytes":
        return _hex(value)
    if type_spelling == "date":
        return _date(value).isoformat()
    if type_spelling == "time":
        return _time(value).isoformat()
    if type_spelling == "timestamp":
        return _instant(value).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    if type_spelling == "uuid":
        return str(_as_uuid(value))
    if type_spelling in ("boolean", "int32", "int64", "float32", "float64", "string"):
        return value
    raise DocumentEncodingError(f"{type_spelling!r} names no neutral type this table covers")


def decode_leaf(type_spelling: str, value: Any) -> Any:
    """One document leaf as the value a Column of its own would have carried.

    :func:`encode_leaf`'s inverse, and the read side of "the layout is not
    observable": a member the layout moved into the shared Structured Column must
    arrive in a result row spelled exactly as the same member does when it holds a
    Column, or one logical value would differ by layout.

    Ten of the twelve rows are the identity, because the document spelling IS what
    the corpus authors and what a Column of that type reads back as here. The two
    that are not are the two whose spellings were chosen for the document rather
    than for the wire: a ``decimal(p, s)`` is stored as its exact digit string and
    read back from a Column as a number, and a ``timestamp`` is stored at UTC with
    a ``Z`` terminator and read back from a Column with an explicit ``+00:00``
    offset.
    """
    if value is None:
        return None
    decimal_type = _DECIMAL_TYPE.match(type_spelling)
    if decimal_type is not None:
        return decimal.Decimal(str(value))
    if type_spelling == "timestamp":
        return _instant(value).isoformat()
    if type_spelling in _IDENTITY_DECODED:
        return value
    raise DocumentEncodingError(f"{type_spelling!r} names no neutral type this table covers")


def comparison_text(type_spelling: str, value: Any) -> str:
    """The exact characters a dialect's text extraction returns for ``value``'s
    encoding — what a predicate binds where the declared type compares as extracted
    text rather than through a cast.

    Defined for exactly the six text-compared types, and for each it is the encoded
    string's own characters, unquoted and unescaped.
    """
    if not is_text_compared(type_spelling):
        raise DocumentEncodingError(
            f"{type_spelling!r} has no comparison text: it compares through a dialect cast, "
            "which binds the managed value"
        )
    encoded = encode_leaf(type_spelling, value)
    if not isinstance(encoded, str):  # pragma: no cover - the six all encode to strings
        raise DocumentEncodingError(f"{type_spelling!r} did not encode to text")
    return encoded


def encode_document(container: dict[str, Any], values: Any) -> Any:
    """One occurrence's neutral write input as the document it stores.

    ``container`` is a descriptor ``valueObject`` / ``nestedValueObject`` mapping and
    ``values`` the case-authored value at that occurrence — a mapping for a ``one``, an
    ordered sequence of them for a ``many``. Members are emitted in the declaration's
    own order (leaves, then nested occurrences), so one set of values produces one
    document; a member the input omits contributes no key, an explicitly null one
    contributes JSON null, and a ``many`` occurrence always contributes its array,
    empty where the input supplies nothing.
    """
    if container.get("multiplicity", "one") == "many":
        elements = values if isinstance(values, list) else []
        return [_encode_element(container, element) for element in elements]
    if values is None:
        return None
    return _encode_element(container, values)


def _encode_element(container: dict[str, Any], value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    element: dict[str, Any] = dict(value)
    document: dict[str, Any] = {}
    for attribute in container.get("attributes", []):
        name = attribute["name"]
        if name in element:
            document[name] = encode_leaf(attribute["type"], element.pop(name))
    for nested in container.get("valueObjects", []):
        name = nested["name"]
        many = nested.get("multiplicity", "one") == "many"
        if name in element:
            document[name] = encode_document(nested, element.pop(name))
        elif many:
            document[name] = []
    # A key no member declares is an unknown key: valid data written by some other
    # version of an application, which a fixture may seed deliberately. It is carried
    # through unencoded — the shape says nothing about how to spell it.
    document.update(element)
    return document


def encode_candidate(container: dict[str, Any], constraints: dict[tuple[str, ...], Any]) -> Any:
    """The containment candidate a to-many equality binds: the object carrying exactly
    the constrained paths, each at its declared position under ``container`` and
    spelled by the encoding table, and no other key.

    Containment compares JSON values, so neither comparison form is what it binds: a
    ``boolean`` in the form its cast comparison binds is MariaDB's ``1``, and a
    candidate ``{"flag": 1}`` matches no element storing a JSON boolean. A path the
    constraints do not name is left unconstrained rather than absent, so it contributes
    no key at all — including a ``many`` member, which therefore contributes no ``[]``.
    """
    if not constraints:
        raise DocumentEncodingError("a containment candidate carries at least one constrained path")
    candidate: dict[str, Any] = {}
    for path, value in constraints.items():
        current = container
        nest = candidate
        for segment in path[:-1]:
            nested = _nested(current, segment)
            if nested is None:
                raise DocumentEncodingError(f"{'.'.join(path)}: {segment!r} names no occurrence")
            current = nested
            nest = nest.setdefault(segment, {})
        leaf = _attribute(current, path[-1])
        if leaf is None:
            raise DocumentEncodingError(f"{'.'.join(path)}: does not reach a declared leaf")
        nest[path[-1]] = encode_leaf(leaf["type"], value)
    return candidate


def _nested(container: dict[str, Any], name: str) -> dict[str, Any] | None:
    for nested in container.get("valueObjects", []):
        if nested["name"] == name:
            return nested
    return None


def _attribute(container: dict[str, Any], name: str) -> dict[str, Any] | None:
    for attribute in container.get("attributes", []):
        if attribute["name"] == name:
            return attribute
    return None


def _exact_decimal(value: Any, scale: int) -> str:
    """The exact decimal spelling: a ``-`` only for a value below zero, the integer
    digits with no leading zero, and — when ``scale > 0`` — ``.`` and exactly ``scale``
    fraction digits.

    A wire decimal rides as a JSON number, so it is read through its shortest
    round-tripping text rather than through the binary expansion of the float that
    carried it; an already-exact string spelling is read as itself.
    """
    text = repr(value) if isinstance(value, float) else str(value)
    try:
        exact = decimal.Decimal(text)
    except decimal.InvalidOperation as exc:
        raise DocumentEncodingError(f"{value!r} is not an exact decimal") from exc
    sign, digits, exponent = exact.as_tuple()
    if not isinstance(exponent, int) or exponent + scale < 0:
        raise DocumentEncodingError(f"{value!r} needs more than {scale} fraction digit(s)")
    unscaled = 0
    for digit in digits:
        unscaled = unscaled * 10 + digit
    unscaled *= 10 ** (exponent + scale)
    padded = str(unscaled).rjust(scale + 1, "0")
    body = f"{padded[:-scale]}.{padded[-scale:]}" if scale else padded
    return f"-{body}" if sign and unscaled else body


def _hex(value: Any) -> str:
    """Lowercase hexadecimal, two digits per byte, no prefix or separator.

    A ``bytes`` wire literal reaches YAML two ways — the ``!!binary`` tag, which
    ``safe_load`` materializes as bytes, and a plain hex string — and both spell the
    same octets.
    """
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, str):
        try:
            return bytes.fromhex(value).hex()
        except ValueError as exc:
            raise DocumentEncodingError(f"{value!r} is not a hex octet spelling") from exc
    raise DocumentEncodingError(f"{value!r} is not a byte sequence")


def _date(value: Any) -> _dt.date:
    if isinstance(value, _dt.datetime):
        raise DocumentEncodingError(f"{value!r} is an instant, not a calendar date")
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        return _parsed(_dt.date.fromisoformat, value)
    raise DocumentEncodingError(f"{value!r} is not a date")


def _time(value: Any) -> _dt.time:
    if isinstance(value, _dt.time):
        return value
    if isinstance(value, str):
        return _parsed(_dt.time.fromisoformat, value)
    raise DocumentEncodingError(f"{value!r} is not a time of day")


def _instant(value: Any) -> _dt.datetime:
    """``value`` as a UTC instant. A naive spelling names no absolute instant and is
    refused rather than assumed local."""
    parsed = value if isinstance(value, _dt.datetime) else None
    if isinstance(value, str):
        parsed = _parsed(_dt.datetime.fromisoformat, value)
    if parsed is None:
        raise DocumentEncodingError(f"{value!r} is not an instant")
    if parsed.tzinfo is None:
        raise DocumentEncodingError(f"{value!r} carries no offset, so it names no instant")
    return parsed.astimezone(_dt.UTC)


def _as_uuid(value: Any) -> _uuid.UUID:
    if isinstance(value, _uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return _uuid.UUID(value)
        except ValueError as exc:
            raise DocumentEncodingError(f"{value!r} is not a UUID") from exc
    raise DocumentEncodingError(f"{value!r} is not a UUID")


def _parsed(parse: Any, literal: str) -> Any:
    try:
        return parse(literal)
    except ValueError as exc:
        raise DocumentEncodingError(f"{literal!r} is not a well-formed ISO-8601 value") from exc
