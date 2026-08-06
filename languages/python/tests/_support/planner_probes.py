"""Shared inputs for suites that drive the unit-of-work shell, the
write-lowering seam, or the Write Planner directly, without a full
``Database``: the Subject Identity every Planning Request needs, and the
Entity Identity and observation key a corpus entity's rows carry.
"""

from __future__ import annotations

from typing import Final

from parallax.core.metamodel import EntityIdentity
from parallax.core.unit_work import ObjectKey, SubjectIdentity

__all__ = [
    "CORPUS_NAMESPACE",
    "TEST_SUBJECT_IDENTITY",
    "corpus_entity",
    "corpus_object_key",
]

# An arbitrary nonempty Subject Identity: `m-unit-work` requires one on every
# Planning Request and guarantees it is never inspected, so any value serves
# every suite here identically.
TEST_SUBJECT_IDENTITY: Final[SubjectIdentity] = SubjectIdentity("test-subject")

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
