from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final

from parallax.conformance.workloads import canonical_source

WRITE_SOURCES: Final = (
    "tests/unit/_write_lowering_support.py",
    "tests/unit/_structural_geometry_support.py",
    "tests/unit/_scalar_type_support.py",
    "tests/unit/_workload_spelling_support.py",
)

FEATURE_SOURCE: Final = "tests/unit/_feature_boundary_support.py"


def write_digest(sources: Sequence[str], manifests: Sequence[str]) -> str:
    """The write-lowering identity of ``sources``, in :data:`WRITE_SOURCES`
    order, and the frozen structural and scalar-type ``manifests``."""
    digest = hashlib.sha256()
    for index, source in enumerate(sources):
        omitted = frozenset({"write_lowering_digest"}) if index == 0 else frozenset[str]()
        digest.update(canonical_source(source, omit_functions=omitted))
        digest.update(b"\0")
    for manifest in manifests:
        digest.update(manifest.encode("utf-8"))
    return digest.hexdigest()


def feature_digest(source: str) -> str:
    """The feature-boundary identity of the :data:`FEATURE_SOURCE` text ``source``."""
    canonical = canonical_source(source, omit_functions=frozenset({"workload_digest"}))
    return hashlib.sha256(canonical).hexdigest()
