"""``parallax.core.wire`` — the canonical Wire Value table (m-wire).

One function answers "how is a value of this declared type written out", and
:func:`decode_wire` inverts it over exactly that function's own codomain. Both
consumers of a written neutral value call these: the document codec, which stores
a leaf inside a structured column, and the wire materializer, which renders a
Wire Snapshot's leaves for transport. Sharing the functions is what makes the two
agree structurally rather than by discipline — a divergence would need a second
table, and there is nowhere to put one.

The string spellings are comparison-significant, not house style. SQL compares
the six text-compared types by comparing extracted document text directly, so
changing one changes predicate and ordering results and MUST move `m-dialect`'s
corresponding decision with it (`m-document-codec` "Portable leaf encodings").
"""

from __future__ import annotations

import datetime as _dt
import decimal as _decimal
import uuid as _uuid
from typing import cast

from parallax.core.base import (
    Boolean,
    Bytes,
    Date,
    Decimal,
    Float32,
    Float64,
    Int32,
    Int64,
    Json,
    NeutralType,
    String,
    Time,
    Timestamp,
    Uuid,
    decode_neutral_literal,
    matches_neutral_type,
)

__all__ = ["WireEncodingError", "decode_wire", "encode_wire"]

# The widest decimal rendering `%.{p}g` can need to round-trip a binary64, and so the
# upper bound of the shortest-number search below.
_MAX_SIGNIFICANT_DIGITS = 17


class WireEncodingError(Exception):
    """A value and the Neutral Type declared for it do not pair through this table.

    Raised rather than encoded or decoded, in both directions: a value outside the
    declared value space has no spelling here, and a written value that is not the one
    spelling the table gives some value of that space is the encoding of nothing here.
    The table is total over the type algebra and says nothing about either, and
    inventing an answer for one is exactly what this module exists to prevent.
    """


def encode_wire(neutral_type: NeutralType, value: object) -> object:
    """``value``'s one canonical spelling under ``neutral_type`` (m-wire).

    Every Neutral Type has exactly one, so two writers of one value produce one
    result. The answer is a portable JSON value — never a driver value, a rendered
    text, or a provider-native handle.

    The open upper bound of a temporal interval is refused here rather than spelled:
    it is not a member of any value space, and its own canonical literal is
    `m-core`'s (:data:`~parallax.core.base.INFINITY_LITERAL`).
    """
    if not matches_neutral_type(value, neutral_type):
        raise WireEncodingError(
            f"{value!r} is not a member of the declared value space {neutral_type!r}"
        )
    match neutral_type:
        case Boolean() | Int32() | Int64() | String() | Json():
            return value
        case Float32() | Float64():
            return _shortest_float(cast("float", value), neutral_type)
        case Decimal(_precision, scale):
            return _exact_decimal(cast("_decimal.Decimal", value), scale)
        case Bytes():
            return cast("bytes", value).hex()
        case Date():
            return cast("_dt.date", value).isoformat()
        case Time():
            return cast("_dt.time", value).isoformat()
        case Timestamp():
            dt = cast("_dt.datetime", value).astimezone(_dt.UTC)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
        case Uuid():
            return str(cast("_uuid.UUID", value))


def decode_wire(neutral_type: NeutralType, value: object) -> object:
    """The neutral value ``value`` is the canonical spelling of.

    :func:`encode_wire`'s inverse, and its domain is that function's own codomain: a
    written value must both name a member of the declared value space and be the ONE
    spelling this table gives that member. The second condition is what a parse alone
    does not ask. A ``decimal(p, s)`` short of its declared scale, uppercase
    hexadecimal, a ``timestamp`` at a non-UTC offset, an uppercase or hyphenless UUID,
    and a float number that is not the shortest one for the value it names all decode
    into their declared type and are still a DIFFERENT spelling from the one a writer
    of that value would have produced — and the six text-compared spellings are the
    characters SQL compares and orders by, so reading one back as an ordinary value
    would answer with a row that no predicate over the same member finds.

    Raised rather than repaired: this module defines no defaulting and never invents a
    value for data that contradicts its declared type.
    """
    decoded = decode_neutral_literal(value, neutral_type)
    if matches_neutral_type(decoded, neutral_type) and encode_wire(neutral_type, decoded) == value:
        return decoded
    raise WireEncodingError(
        f"{value!r} is not the canonical spelling of any {neutral_type!r} value"
    )


def _exact_decimal(value: _decimal.Decimal, scale: int) -> str:
    """The exact decimal spelling: a ``-`` only for a value below zero, the integer
    digits with no leading zero (a single ``0`` when the integer part is zero), and —
    when ``scale > 0`` — ``.`` and exactly ``scale`` fraction digits.

    Rescaling is exact by construction rather than by a rounding context: membership
    already established the value needs no more fraction digits than ``scale`` admits,
    so the shift below only ever pads with zeros, at any precision.
    """
    sign, digits, exponent = value.as_tuple()
    unscaled = 0
    for digit in digits:
        unscaled = unscaled * 10 + digit
    unscaled *= 10 ** (cast("int", exponent) + scale)
    padded = str(unscaled).rjust(scale + 1, "0")
    body = f"{padded[:-scale]}.{padded[-scale:]}" if scale else padded
    return f"-{body}" if sign and unscaled else body


def _shortest_float(value: float, neutral_type: Float32 | Float64) -> float:
    """The number with the fewest significant digits that decodes back to ``value``
    under the declared width, nearest among equally short ones, and — where two are
    equally near — the one whose last significant digit is even.

    All three levels are load-bearing: binary64 ``562949953421312.25`` is decoded from
    both ``562949953421312.2`` and ``562949953421312.3``, so the first two alone still
    admit two numbers. ``%.{p}g`` supplies all three at once, because it renders the
    correctly-rounded ``p``-digit decimal and breaks its own tie to even.

    "Decodes back to" is measured through the decode leg itself, so the phrase cannot
    mean one thing while encoding and another while reading: a ``float32``'s decode
    reads a number at binary32, which is why ``1048576.2`` is admissible for
    ``1048576.25`` at that width and for nothing at binary64.

    The answer is the float, not its rendering: ``20`` and ``20.0`` are one JSON
    number, while ``0.1`` and ``0.10000000000000001`` are two and only the first is
    admissible.
    """
    target = cast("float", decode_neutral_literal(value, neutral_type))
    for precision in range(1, _MAX_SIGNIFICANT_DIGITS + 1):
        candidate = float(f"{target:.{precision}g}")
        if decode_neutral_literal(candidate, neutral_type) == target:
            return candidate
    return target  # pragma: no cover - 17 significant digits always round-trip
