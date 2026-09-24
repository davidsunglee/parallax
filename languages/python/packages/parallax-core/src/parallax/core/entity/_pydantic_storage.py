"""Read Pydantic's slot descriptors directly to bypass authored attribute hooks.

Do not use these accessors for published member reads: requesting their raw
Pydantic storage allocates a dictionary permanently. Use the instance-state
accessors for semantic reads."""

from __future__ import annotations

from typing import Any, Final, cast

from pydantic import BaseModel

__all__ = [
    "MODEL_PRESENCE",
    "MODEL_STORAGE",
    "attach_instance_state",
    "instance_presence",
    "instance_state",
    "replace_instance_presence",
    "replace_instance_state",
]

MODEL_STORAGE: Final = BaseModel.__dict__["__dict__"]
"""Pydantic's own slot descriptor for the instance storage every model carries.

Exported beside the functions over it because a caller layering its own
presentation on this name reaches it once per read of every model in the
process, where the extra call the functions cost is measurable.
"""

MODEL_PRESENCE: Final = BaseModel.__dict__["__pydantic_fields_set__"]
"""Pydantic's own slot descriptor for the populated-member set beside it."""


def instance_state(value: BaseModel) -> dict[str, Any]:
    """``value``'s own attribute storage, as the mutable mapping it is.

    Creates one on a value that holds none, which a published value does — so a
    read that only means to see what a value holds belongs on the backing's own
    reader instead, and this is for the callers that mean the storage.
    """
    return cast("dict[str, Any]", MODEL_STORAGE.__get__(value))


def attach_instance_state(value: BaseModel, name: str, state: object) -> None:
    """Write ``state`` into ``value``'s storage under ``name``."""
    instance_state(value)[name] = state


def replace_instance_state(value: BaseModel, state: dict[str, object]) -> None:
    """Make ``state`` the whole of ``value``'s storage."""
    MODEL_STORAGE.__set__(value, state)


def instance_presence(value: BaseModel) -> set[str]:
    """The populated-member set ``value`` itself holds.

    Raises ``AttributeError`` for a value that holds none, which a shell awaiting
    publication and a published value both do.
    """
    return cast("set[str]", MODEL_PRESENCE.__get__(value))


def replace_instance_presence(value: BaseModel, populated: set[str]) -> None:
    """Make ``populated`` the whole of ``value``'s own populated-member set."""
    MODEL_PRESENCE.__set__(value, populated)
