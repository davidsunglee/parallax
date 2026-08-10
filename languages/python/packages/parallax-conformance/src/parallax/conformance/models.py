"""Corpus model ingestion (the conformance descriptor frontend).

The adapter path builds the metamodel by **direct ingestion** of canonical YAML
descriptors from ``core/compatibility/models/*.yaml`` — corpus cases never
require Python entity classes. Each model file goes through the public
:func:`~parallax.descriptor.domain_model_from_document` door, which runs the
descriptor schema, value, and Model Formation phases in one call, and the
accepted :class:`~parallax.core.metamodel.Metamodel` behavioral modules consume
is read out of the sealed Domain Model through the first-party
``parallax.core.entity._model.model_of`` seam.

The accepted model enumerates its Entities canonically, so a corpus model's own
AUTHORING order is not recoverable from it. `m-case-format`'s default-target
convention for a case naming no target ends at "the model's own first entity",
which is a fact about the document; :func:`declared_entity_spellings` is where
that fact is read, and it is the only reason this module still looks at a
decoded document after forming one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from parallax.conformance import case_format
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor import domain_model_from_document

__all__ = [
    "accepted_model",
    "declared_entity_spellings",
    "default_models_dir",
    "load_model",
    "load_models",
    "read_document",
]


def default_models_dir() -> Path:
    """The corpus model directory, discovered relative to the working directory."""
    return case_format.find_repo_root() / "core" / "compatibility" / "models"


def read_document(path: Path) -> Mapping[str, object]:
    """Decode one canonical model descriptor, checking only that it is a mapping.

    No descriptor phase runs here: a document that is not a mapping at all names
    no door's input, and every other defect is :func:`accepted_model`'s to
    report in the phase order the public door fixes.
    """
    document = case_format.safe_load_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path.name}: model descriptor is not a mapping")
    return cast("Mapping[str, object]", document)


def accepted_model(document: Mapping[str, object]) -> AcceptedMetamodel:
    """The accepted Metamodel ``document`` forms into.

    One call of the public descriptor door, so the phase order is the door's:
    :class:`~parallax.descriptor.DescriptorSchemaError` for a canonical-schema
    violation, :class:`~parallax.descriptor.DescriptorValueError` for a
    schema-valid but unconstructible value, then
    :class:`~parallax.core.model_formation.MetamodelValidationError` for every
    semantic model rule — all before this returns.
    """
    return model_of(domain_model_from_document(document))


def declared_entity_spellings(document: Mapping[str, object]) -> tuple[str, ...]:
    """The Entities ``document`` declares, canonically spelled, in its own
    authoring order.

    Reads the canonical schema's two top-level forms (``entity:`` for one,
    ``entities:`` for several) and nothing else, so it answers for a document
    that never forms as readily as for one that does. The accepted model
    enumerates canonically, which is why the ORDER cannot be taken from there.

    Each spelling is ``<namespace>.<name>``, exactly as
    :attr:`~parallax.core.metamodel.EntityIdentity.canonical` composes one, and
    bare only for an Entity the document declares ownerless. A selection this
    module makes is not an authored reference, so it must not be handed on as a
    bare local name: a bare spelling two namespaces share names both Entities
    and therefore neither, and a bare spelling an ownerless Entity also carries
    names that OTHER Entity exactly.
    """
    single = document.get("entity")
    if isinstance(single, Mapping):
        return (_canonical_spelling(cast("Mapping[str, object]", single)),)
    several = document.get("entities")
    if not isinstance(several, Sequence) or isinstance(several, str | bytes):
        return ()
    return tuple(
        _canonical_spelling(cast("Mapping[str, object]", entry))
        for entry in cast("Sequence[object]", several)
        if isinstance(entry, Mapping)
    )


def _canonical_spelling(declaration: Mapping[str, object]) -> str:
    name = str(declaration.get("name", ""))
    namespace = declaration.get("namespace")
    return f"{namespace}.{name}" if isinstance(namespace, str) and namespace else name


def load_model(path: Path) -> AcceptedMetamodel:
    """The accepted Metamodel one canonical model descriptor file forms into."""
    return accepted_model(read_document(path))


def load_models(directory: Path | None = None) -> dict[str, AcceptedMetamodel]:
    """Form every corpus model, keyed by file stem (default: the discovered corpus)."""
    root = directory if directory is not None else default_models_dir()
    return {path.stem: load_model(path) for path in sorted(root.glob("*.yaml"))}
