"""Corpus model ingestion (the conformance descriptor frontend).

The adapter path builds the metamodel by **direct ingestion** of canonical YAML
descriptors from ``core/compatibility/models/*.yaml`` — corpus cases never
require Python entity classes. Each model file is deserialized through the
``m-descriptor`` deserializer into a :class:`~parallax.core.descriptor.Metamodel`.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from parallax.conformance import case_format
from parallax.core.descriptor import Metamodel, deserialize

__all__ = ["default_models_dir", "load_model", "load_models"]


def default_models_dir() -> Path:
    """The corpus model directory, discovered relative to the working directory."""
    return case_format.find_repo_root() / "core" / "compatibility" / "models"


def load_model(path: Path) -> Metamodel:
    """Ingest one canonical model descriptor into a :class:`Metamodel`."""
    document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name}: model descriptor is not a mapping")
    return deserialize(cast("Mapping[str, object]", document))


def load_models(directory: Path | None = None) -> dict[str, Metamodel]:
    """Ingest every corpus model, keyed by file stem (default: the discovered corpus)."""
    root = directory if directory is not None else default_models_dir()
    return {path.stem: load_model(path) for path in sorted(root.glob("*.yaml"))}
