"""Package-internal narrow-position resolution (COR-3 Phase 7 increment 7
round-3, P2/Standards 2).

The single seam behind an AUTHORED ``narrow(...)``'s resolved effective
concrete-subtype set: the alphabetically-sorted union of
:func:`~parallax.core.inheritance.effective_concrete_subtypes` over every
authored subtype name. `m-deep-fetch`'s own dedup-identity derivation
(``parallax.core.deep_fetch._resolve_position``'s narrowed branch) and the
entity frontend's narrowed-view key derivation
(``parallax.core.entity.graph_state``) both call this SAME function, so the
two can never drift -- the duplication a confirmation-pass review found
between them (``expressions.py:609`` previously, now removed) is fixed by
centralizing here rather than by leaving each caller its own copy.

A non-underscored function in an underscore-prefixed internal module: every
DAG-permitted consumer of :mod:`parallax.core.inheritance` (this package
carries no forbidden edge to/from ``parallax.core.entity`` or
``parallax.core.deep_fetch`` -- the two mutually-forbidden scopes this seam
must bridge) can import ``resolve_narrow_position`` by name with no Pyright
``reportPrivateUsage`` suppression (the imported NAME carries no leading
underscore -- only this MODULE's own does), while the leading underscore
keeps it out of :mod:`parallax.core.inheritance`'s own public surface
(never re-exported through that package's ``__init__.py``, never reachable
from ``parallax.core``'s curated ``__all__``).
"""

from __future__ import annotations

from collections.abc import Sequence

from parallax.core.descriptor import Metamodel
from parallax.core.inheritance import effective_concrete_subtypes

__all__ = ["resolve_narrow_position"]


def resolve_narrow_position(meta: Metamodel, names: Sequence[str]) -> tuple[str, ...]:
    """The alphabetically-sorted union of :func:`effective_concrete_subtypes`
    over every one of ``names`` -- an authored ``narrow(...)``'s resolved
    effective concrete-subtype set (a non-polymorphic name's own trivial
    one-name set either way, via :func:`effective_concrete_subtypes` itself)."""
    resolved: set[str] = set()
    for name in names:
        resolved.update(effective_concrete_subtypes(meta, name))
    return tuple(sorted(resolved))
