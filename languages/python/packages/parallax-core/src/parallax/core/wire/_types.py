from __future__ import annotations

from collections.abc import Mapping

type WireValue = bool | int | float | str | list["WireValue"] | Mapping[str, "WireValue"] | None
"""The recursive JSON data model accepted and returned by the Wire Codec."""
