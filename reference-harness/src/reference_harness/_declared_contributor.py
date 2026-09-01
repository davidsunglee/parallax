"""Declared scalar facts retained beside one physical column contributor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import portable_literal


@dataclass(frozen=True, slots=True)
class _TemporalInfinity:
    pass


TEMPORAL_INFINITY = _TemporalInfinity()


@dataclass(frozen=True, slots=True)
class DeclaredContributor:
    """The declaration facts needed to spell and convert one contributed column."""

    neutral_type: str
    max_length: int | None = None

    def fixture_value(self, value: Any) -> Any:
        """Decode one canonical fixture value for provider storage."""
        if value is None:
            return None
        if self._is_temporal_infinity(value):
            return TEMPORAL_INFINITY
        return portable_literal.decode(value, self.neutral_type)

    def provider_bind(self, value: Any) -> Any:
        """Convert a modeled statement bind without guessing from its carrier."""
        if value is None:
            return None
        if self._is_temporal_infinity(value):
            return TEMPORAL_INFINITY
        try:
            canonical = portable_literal.canonicalize_observed(value, self.neutral_type)
            return portable_literal.decode_canonical(canonical, self.neutral_type)
        except portable_literal.PortableLiteralError:
            return value

    def observed_wire(self, value: Any) -> Any:
        """Project one provider observation to canonical Wire when possible."""
        if value is None or self._is_temporal_infinity(value):
            return value
        if self.neutral_type == "bytes" and isinstance(value, (bytes, bytearray, memoryview)):
            value = bytes(value)
        try:
            return portable_literal.canonicalize_observed(value, self.neutral_type)
        except portable_literal.PortableLiteralError:
            return value

    def _is_temporal_infinity(self, value: Any) -> bool:
        return self.neutral_type == "timestamp" and value == "infinity"
