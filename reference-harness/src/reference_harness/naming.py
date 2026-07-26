"""Independent portable naming operations used by the reference harness."""

from __future__ import annotations


def default_column_name(name: str) -> str:
    """Return m-descriptor's default physical column for a member name."""
    return "".join(
        f"_{character.lower()}" if "A" <= character <= "Z" else character for character in name
    )
