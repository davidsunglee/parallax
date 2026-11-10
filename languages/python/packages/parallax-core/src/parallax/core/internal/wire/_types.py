from __future__ import annotations

from collections.abc import Mapping

type WireValue = bool | int | float | str | list["WireValue"] | Mapping[str, "WireValue"] | None
"""The recursive JSON data model accepted and returned by the Wire Codec, and one
position in a Wire result: a canonical Wire Value, a nested Value Object mapping,
an included Entity node, or an ordered collection of either.

Structural rather than nominal, deliberately: a runtime Wire result value is a
frozen built-in subclass, so it satisfies this alias while remaining directly
JSON-serializable and structurally equal to the plain value it mirrors. That
freezing is a runtime property rather than a static one, and it holds at every
depth against every mutation reaching a value through the instance; the base
descriptors a caller can reach around the instance for
(``dict.__setitem__(value, ...)``, ``list.append(value, ...)``) stay open. A
``Mapping`` member admits every immutable mapping without promising mutation;
spelling immutability statically instead, through public frozen list and mapping
types, would make every ordinary mapping statically unusable as Parallax input."""
