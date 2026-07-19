"""Cross-version class-body annotation recovery for the entity metaclasses.

Both entity metaclasses -- :class:`~parallax.core.entity.base.EntityMeta` and
:class:`~parallax.core.entity.value_object.ValueObjectMeta` -- read the live
``Attr[T]`` / ``Rel[T]`` / ``VoField`` objects straight out of the class-body
``namespace`` their ``__new__`` receives (the model modules deliberately omit
``from __future__ import annotations`` so those objects stay live rather than
stringized). Both metaclasses previously carried an identical copy of this read.

Centralizing it in a shared leaf -- rather than having either metaclass import
the reader FROM the other -- keeps both edges cycle-free: ``base.py`` already
imports ``value_object.py`` at module level (``ValueObject``, ``to_document``,
...), so a NEW module-level edge from ``value_object.py`` back to ``base.py``
would close a runtime import cycle. This leaf imports neither metaclass module,
so both may import it freely. (Both submodules live in the ONE
``parallax.core.entity`` import-linter support scope, so an intra-scope import
is DAG-legal on its own -- the constraint avoided here is the runtime import
cycle, not any forbidden DAG edge.)

A non-underscored function in an underscore-prefixed internal module (mirroring
:mod:`parallax.core.entity._validation`): importable by both metaclass modules
with no Pyright ``reportPrivateUsage`` suppression (the imported NAME carries no
leading underscore -- only this MODULE's own does), never re-exported through
``entity/__init__.py``, so it adds no name to the entity package's public surface.
"""

from __future__ import annotations

import sys
from typing import Any

__all__ = ["class_body_annotations"]


def class_body_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    """The class-body annotations, read from the metaclass ``namespace`` cross-version.

    On Python 3.12/3.13 the live ``Attr[T]`` / ``Rel[T]`` / ``VoField`` objects sit
    eagerly in ``namespace["__annotations__"]``. Under PEP 649 / PEP 749 (Python
    3.14+) annotations are deferred: the namespace carries no ``__annotations__``
    but a ``__annotate_func__`` instead (see :func:`_resolve_deferred`). The
    returned mapping is always a fresh copy the caller may freely mutate.
    """
    eager = namespace.get("__annotations__")
    if eager is not None:
        return dict(eager)
    # A REAL class namespace never carries ``__annotate_func__`` on 3.12/3.13, so in
    # production ``annotate`` is ``None`` there; only a 3.14+ class body reaches the
    # deferred resolver (a synthetic namespace drives the edge under test).
    annotate = namespace.pop("__annotate_func__", None)
    if annotate is None:
        return {}
    return _resolve_deferred(annotate)


def _resolve_deferred(annotate: object) -> dict[str, Any]:
    """Recover deferred (PEP 649 / PEP 749) class-body annotations via ``annotationlib``.

    Evaluated in ``VALUE`` format to recover the same live objects the eager path
    returns; the caller has already popped ``__annotate_func__`` from the namespace
    so the resolved ``__annotations__`` the metaclass writes back stays authoritative
    for Pydantic and the finished class.

    Both arms -- the pre-3.14 ``{}`` short-circuit and the 3.14+ ``annotationlib``
    resolution -- are exercised on every interpreter lane by
    ``tests/unit/test_class_body_annotations.py``, which forces the module's view of
    ``sys.version_info`` and injects a fake ``annotationlib``; a final Python-3.14-only
    test runs the real stdlib module for end-to-end fidelity.

    The ``sys.version_info`` guard also keeps the 3.14-only ``annotationlib`` import
    off Pyright's type-checked path: Pyright is pinned to ``pythonVersion 3.12``, so
    it narrows the guard to always-true and treats the import (and its
    partially-typed ``annotationlib`` surface) as unreachable on every lane.
    """
    if sys.version_info < (3, 14):
        return {}
    import annotationlib  # 3.14 stdlib (PEP 649 / PEP 749)

    return dict(annotationlib.call_annotate_function(annotate, annotationlib.Format.VALUE))
