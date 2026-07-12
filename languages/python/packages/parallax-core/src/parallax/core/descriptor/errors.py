"""Descriptor-scope errors (m-descriptor)."""

from __future__ import annotations

__all__ = ["DescriptorError"]


class DescriptorError(ValueError):
    """A descriptor document violates the m-descriptor structural contract."""
