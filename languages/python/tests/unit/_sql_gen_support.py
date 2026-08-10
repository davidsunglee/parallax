"""Corpus models — accepted, as descriptor records, and Entity lookup.

`compile_read` and `compile_write_predicate` take an accepted Metamodel and the
queried Entity's own Metadata, so every suite needs two things: a formed model
and a way to name an Entity the way a corpus case does — by its bare declared
name. Both live here so no suite restates them.

The descriptor RECORD graph lives here too, and only here. The shipped adapter
reaches a corpus model through the public ``domain_model_from_*`` doors alone, so
nothing in production reads records any more; what still needs them is the
`m-descriptor` suites that are ABOUT the record graph, and the suites whose
synthetic witness is a model shape no canonical document encodes — a missing
table, a composite primary key — which the document door refuses at its schema
phase before the rule under test can run.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from functools import cache

from parallax.conformance import models
from parallax.core._formation_profile import form_metamodel
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.descriptor._adapter import unresolved_metamodel
from parallax.descriptor._ingest import ingest_document
from parallax.descriptor._records import Metamodel as DescriptorMetamodel


@cache
def corpus() -> dict[str, Metamodel]:
    """Every corpus model formed, keyed by file stem.

    Cached because the whole corpus is parsed and formed once per session and
    every suite reads the same immutable models.
    """
    return models.load_models()


def model(stem: str) -> Metamodel:
    """The formed corpus model named ``stem``."""
    return corpus()[stem]


@cache
def corpus_records() -> dict[str, DescriptorMetamodel]:
    """Every corpus model as an unformed descriptor record graph, by file stem."""
    directory = models.default_models_dir()
    return {
        path.stem: ingest_document(models.read_document(path))
        for path in sorted(directory.glob("*.yaml"))
    }


def records(stem: str) -> DescriptorMetamodel:
    """The corpus model named ``stem``, as parsed descriptor records."""
    return corpus_records()[stem]


def formed(records: DescriptorMetamodel) -> Metamodel:
    """Form hand-built descriptor records into an accepted model.

    A suite that needs a model shape the corpus does not carry authors it as
    records and forms it here. This is the RECORD-level route, and it is a test
    seam alone: the shipped adapter reaches a corpus model through the public
    ``domain_model_from_*`` doors, which gate on the canonical schema first. A
    suite whose synthetic witness is deliberately unformable, or whose records
    spell something the document schema has no encoding for, has no public door
    to go through, so the adaptation and formation steps are composed here
    instead — beside the descriptor records those suites already author.
    """
    return form_metamodel(unresolved_metamodel(records))


def target(model: Metamodel, name: str) -> EntityMetadata:
    """The Entity ``name`` denotes in ``model``, named as a corpus case names it.

    A case authors a bare declared name and every corpus Entity is namespaced,
    so the bare name is matched against the model's own canonical enumeration
    rather than assumed ownerless.
    """
    for entity in model.entities:
        if entity.identity.name == name:
            return entity
    raise KeyError(name)
