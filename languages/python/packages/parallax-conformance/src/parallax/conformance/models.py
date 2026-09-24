from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from parallax.conformance import case_format
from parallax.core.entity import DomainModel
from parallax.core.entity._model import model_of
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.descriptor import domain_model_from_document

__all__ = [
    "accepted_model",
    "accepted_model_of",
    "declared_entity_spellings",
    "default_models_dir",
    "domain_model",
    "load_domain_model",
    "load_domain_models",
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


def domain_model(document: Mapping[str, object]) -> DomainModel:
    """The descriptor-backed Domain Model ``document`` forms into.

    One call of the public descriptor door, so the phase order is the door's:
    :class:`~parallax.descriptor.DescriptorSchemaError` for a canonical-schema
    violation, :class:`~parallax.descriptor.DescriptorValueError` for a
    schema-valid but unconstructible value, then
    :class:`~parallax.core.model_formation.MetamodelValidationError` for every
    semantic model rule — all before this returns.

    A Snapshot connection takes the Domain Model rather than the accepted
    Metamodel underneath it, so a lane that connects forms once and reads the
    accepted model back through :func:`accepted_model_of`.
    """
    return domain_model_from_document(document)


def accepted_model_of(model: DomainModel) -> AcceptedMetamodel:
    """``model``'s accepted Metamodel — the behavioral form every core module
    is stated over.

    The first-party ``model_of`` seam, named here so one formation serves both a
    connection and the neutral lanes beside it rather than being repeated.
    """
    return model_of(model)


def accepted_model(document: Mapping[str, object]) -> AcceptedMetamodel:
    """The accepted Metamodel ``document`` forms into.

    The primary loader surface: every caller that names Entities rather than
    connecting reads this, because the accepted Metamodel is what
    ``parallax.core`` is stated over.
    """
    return accepted_model_of(domain_model(document))


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


def load_domain_model(path: Path) -> DomainModel:
    """The Domain Model one canonical model descriptor file forms into."""
    return domain_model(read_document(path))


def load_domain_models(directory: Path | None = None) -> dict[str, DomainModel]:
    """Form every corpus model as a Domain Model, keyed by file stem."""
    root = directory if directory is not None else default_models_dir()
    return {path.stem: load_domain_model(path) for path in sorted(root.glob("*.yaml"))}
