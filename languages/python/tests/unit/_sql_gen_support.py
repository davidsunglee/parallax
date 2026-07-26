"""Accepted models and Entity lookup for the ``m-sql`` suites.

`compile_read` and `compile_write_predicate` take an accepted Metamodel and the
queried Entity's own Metadata, so every suite needs two things: a formed model
and a way to name an Entity the way a corpus case does — by its bare declared
name. Both live here so no suite restates them.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

from functools import cache

from parallax.conformance import models
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.descriptor._records import Metamodel as DescriptorMetamodel


@cache
def corpus() -> dict[str, Metamodel]:
    """Every corpus model formed, keyed by file stem.

    Cached because the whole corpus is parsed and formed once per session and
    every suite reads the same immutable models.
    """
    return {stem: models.accepted_model(meta) for stem, meta in models.load_models().items()}


def model(stem: str) -> Metamodel:
    """The formed corpus model named ``stem``."""
    return corpus()[stem]


def formed(records: DescriptorMetamodel) -> Metamodel:
    """Form hand-built descriptor records into an accepted model.

    A suite that needs a model shape the corpus does not carry authors it as
    records and forms it here, so the synthetic witness goes through the same
    pipeline every other model does.
    """
    return models.accepted_model(records)


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
