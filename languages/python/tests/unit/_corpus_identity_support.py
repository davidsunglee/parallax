"""The Entity Identity and observation key a compatibility-corpus entity's rows
carry, for the unit suites that assert against a write's own resolved key.

Exported names carry no leading underscore: importing an underscored name across
modules is a `reportPrivateUsage` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from typing import Final

from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import ObjectKey

__all__ = [
    "CORPUS_NAMESPACE",
    "corpus_entity",
    "corpus_object_key",
]

# Every compatibility-corpus model declares this namespace, so an entity a case
# document names bare still carries it on the Entity Identity a key names.
CORPUS_NAMESPACE: Final[str] = "parallax.compatibility"


def corpus_entity(name: str) -> EntityIdentity:
    """The Entity Identity a corpus model's locally named entity carries."""
    return EntityIdentity(CORPUS_NAMESPACE, name)


def corpus_object_key(name: str, *primary_key: tuple[str, object]) -> ObjectKey:
    """The :class:`ObjectKey` a corpus entity's object is observed under —
    ``name``'s canonical Entity Identity plus the ordered
    ``(pk-attribute-name, value)`` pairs the row carries."""
    return ObjectKey(corpus_entity(name), primary_key)
