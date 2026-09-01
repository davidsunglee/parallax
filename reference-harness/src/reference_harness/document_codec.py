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

import json
import re
from typing import Any

from . import portable_literal
from .portable_literal import AuthoredInteger, AuthoredNumber

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

_DECIMAL_TYPE = re.compile(r"^decimal\((\d+),\s*(\d+)\)$")


class DocumentEncodingError(Exception):
    """A value and the type its member declares do not pair through this table: a
    value with no document spelling under it, or a stored leaf that is the encoding of
    no value of it."""


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

    A fractional number and integer-token negative zero keep the digits they were
    stored with: a float leaf's canonical spelling is a property of those digits, so
    parsing them into ordinary host numbers here would make ``0.1`` and
    ``0.10000000000000001`` one value and erase the sign from ``-0`` before
    :func:`decode_leaf` could refuse either noncanonical spelling.
    """
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray, memoryview)):
        raw = bytes(raw).decode()
    if isinstance(raw, str):
        return json.loads(raw, parse_float=AuthoredNumber, parse_int=_stored_integer)
    return raw


def _stored_integer(literal: str) -> int:
    return AuthoredInteger(literal) if literal == "-0" else int(literal)


def encode_leaf(type_spelling: str, value: Any) -> Any:
    """``value``'s one document spelling under the declared type.

    The domain is the case corpus's own wire literals — the spelling a neutral value
    rides in YAML — because that is what a case authors and what a conforming writer
    receives. Every type has exactly one document form, so two writers of one value
    produce one document.
    """
    if value is None:
        return None
    try:
        return portable_literal.canonicalize(value, type_spelling)
    except portable_literal.PortableLiteralError as exc:
        raise DocumentEncodingError(str(exc)) from exc


def decode_leaf(type_spelling: str, value: Any) -> Any:
    """One document leaf as the value a Column of its own would have carried.

    :func:`encode_leaf`'s inverse, and the read side of "the layout is not
    observable": a member the layout moved into the shared Structured Column must
    arrive in a result row spelled exactly as the same member does when it holds a
    Column, or one logical value would differ by layout.

    Eight of the twelve rows are the identity, because the document spelling IS what
    the corpus authors and what a Column of that type reads back as here. Four are
    not. Two of those were spelled for the document rather than for the wire: a
    ``decimal(p, s)`` is stored as its exact digit string and read back from a Column
    as a number, and a ``timestamp`` is stored at UTC with a ``Z`` terminator and
    read back from a Column with an explicit ``+00:00`` offset. The other two are
    ``float32`` and ``float64``, whose document number is the shortest one that
    round-trips at the DECLARED width, so it is read as a float of that width.

    A stored value that is not the spelling :func:`encode_leaf` gives some value of
    the declared type is **invalid stored data** (m-document-codec) and raises rather
    than reaching a result row under a member the model types otherwise.
    """
    if value is None:
        return None
    try:
        managed = portable_literal.decode_canonical(value, type_spelling)
        if _DECIMAL_TYPE.match(type_spelling) is not None or type_spelling in (
            "int32",
            "int64",
            "float32",
            "float64",
        ):
            return managed
        if type_spelling == "timestamp":
            return managed.isoformat()
        return value
    except portable_literal.PortableLiteralError as exc:
        if (
            "names no" in str(exc)
            and type_spelling
            not in {
                "boolean",
                "int32",
                "int64",
                "float32",
                "float64",
                "string",
                "bytes",
                "date",
                "time",
                "timestamp",
                "uuid",
                "json",
            }
            and _DECIMAL_TYPE.match(type_spelling) is None
        ):
            raise DocumentEncodingError(
                f"{type_spelling!r} names no neutral type this table covers"
            ) from exc
        raise DocumentEncodingError(
            f"{value!r} is not a {type_spelling!r} encoding — invalid stored data"
        ) from exc


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
