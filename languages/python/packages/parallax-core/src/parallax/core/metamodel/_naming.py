"""Portable member-storage naming (m-metamodel)."""

from __future__ import annotations

__all__ = ["default_column_name"]


def default_column_name(name: str) -> str:
    """Return the portable default column for a canonical member name.

    Each ASCII uppercase letter becomes an underscore followed by its lowercase
    form. Lowercase letters, digits, underscores, and all other code points are
    preserved unchanged. Callers resolve a frontend-specific member spelling to
    its canonical identity before applying this operation.
    """
    return "".join(
        f"_{character.lower()}" if "A" <= character <= "Z" else character for character in name
    )
