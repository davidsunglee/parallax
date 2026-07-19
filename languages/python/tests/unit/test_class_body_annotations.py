"""The shared cross-version class-body annotation reader both entity metaclasses use.

Covers :func:`parallax.core.entity._annotations.class_body_annotations` directly:
the eager (Python 3.12/3.13) path, the no-annotations path, and the deferred
(PEP 649 / PEP 749) ``__annotate_func__`` path. The deferred path's two version arms
are exercised on *every* interpreter by forcing the module's view of
``sys.version_info`` and injecting a fake ``annotationlib``; a final test runs the
real 3.14 stdlib module for end-to-end fidelity.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any, cast

import pytest

from parallax.core.entity._annotations import class_body_annotations

pytestmark = pytest.mark.unit

# The module object under test, fetched without binding its private (underscore)
# name -- so patching its ``sys`` view stays Pyright-clean (no reportPrivateUsage).
_ANNOTATIONS_MODULE = sys.modules[class_body_annotations.__module__]


def test_eager_annotations_are_read() -> None:
    """On 3.12/3.13 the live annotations sit eagerly in ``__annotations__``."""
    assert class_body_annotations({"__annotations__": {"x": int}}) == {"x": int}


def test_eager_annotations_are_copied() -> None:
    """The reader returns a fresh mapping -- mutating it never touches the namespace."""
    source: dict[str, Any] = {"x": int}
    result = class_body_annotations({"__annotations__": source})
    result["y"] = str
    assert source == {"x": int}


def test_empty_namespace_has_no_annotations() -> None:
    """A namespace with neither ``__annotations__`` nor ``__annotate_func__`` is empty."""
    assert class_body_annotations({}) == {}


def test_namespace_without_annotations_is_empty() -> None:
    """A class body that declares no annotations at all reads as ``{}`` (the
    ``annotate is None`` path), even with other namespace members present."""
    assert class_body_annotations({"__module__": "m", "FOO": 1}) == {}


class _FakeFormat:
    """Stand-in for ``annotationlib.Format`` -- only ``VALUE`` is referenced."""

    VALUE = "VALUE"


class _FakeAnnotationlib:
    """Stand-in for the real 3.14 ``annotationlib`` module.

    Mirrors the exact call surface the resolver uses -- ``Format.VALUE`` and
    ``call_annotate_function(annotate, format)`` returning the live-object mapping --
    so the deferred flow runs on interpreters that lack the stdlib module. The real
    signature is validated by ``test_deferred_annotations_use_real_annotationlib``.
    """

    Format = _FakeFormat

    def __init__(self) -> None:
        self.received_format: object = None

    def call_annotate_function(
        self, annotate: Callable[[object], dict[str, Any]], format: object
    ) -> dict[str, Any]:
        self.received_format = format
        return annotate(format)


def _force_version(monkeypatch: pytest.MonkeyPatch, version: tuple[int, int]) -> None:
    """Override only the annotations module's view of ``sys.version_info``."""

    class _FakeSys:
        version_info = version

    monkeypatch.setattr(_ANNOTATIONS_MODULE, "sys", _FakeSys())


def test_deferred_path_short_circuits_before_314(monkeypatch: pytest.MonkeyPatch) -> None:
    """Below 3.14 the resolver short-circuits to ``{}`` (``annotationlib`` is a 3.14
    stdlib module). Forcing the version runs this on every interpreter, covering the
    guard's ``return {}`` arm regardless of the host Python."""
    _force_version(monkeypatch, (3, 13))

    def annotate(_format: object) -> dict[str, Any]:
        return {"x": int}

    namespace: dict[str, Any] = {"__annotate_func__": annotate}
    assert class_body_annotations(namespace) == {}
    assert "__annotate_func__" not in namespace


def test_deferred_path_resolves_via_fake_annotationlib(monkeypatch: pytest.MonkeyPatch) -> None:
    """On 3.14+ the deferred function is called in ``VALUE`` format and its live
    objects are returned. Forcing the version and injecting a fake ``annotationlib``
    runs this on every interpreter, covering the resolution arm regardless of the host
    Python."""
    _force_version(monkeypatch, (3, 14))
    fake = _FakeAnnotationlib()
    monkeypatch.setitem(sys.modules, "annotationlib", cast(ModuleType, fake))

    def annotate(_format: object) -> dict[str, Any]:
        return {"x": int, "y": str}

    namespace: dict[str, Any] = {"__module__": "m", "__annotate_func__": annotate}
    assert class_body_annotations(namespace) == {"x": int, "y": str}
    assert fake.received_format is _FakeFormat.VALUE
    assert "__annotate_func__" not in namespace


@pytest.mark.skipif(
    sys.version_info < (3, 14),
    reason="deferred (__annotate_func__) annotations are PEP 649 / PEP 749, Python 3.14+ only",
)
def test_deferred_annotations_use_real_annotationlib() -> None:
    """End-to-end fidelity on 3.14: the real stdlib ``annotationlib`` recovers the live
    objects from ``__annotate_func__`` and the deferred function is popped so the
    metaclass's own resolved ``__annotations__`` write-back stays authoritative."""

    def annotate(_format: object) -> dict[str, Any]:
        return {"x": int, "y": str}

    namespace: dict[str, Any] = {"__module__": "m", "__annotate_func__": annotate}
    assert class_body_annotations(namespace) == {"x": int, "y": str}
    assert "__annotate_func__" not in namespace
