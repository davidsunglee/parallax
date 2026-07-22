"""Idiomatic entity classes the API-suite graph stories construct statements
over: a mirror of ``models/policy.yaml`` (``Policy`` / ``Coverage`` / ``Claim``,
bitemporal entities that also relate, COR-3 Phase 7 increment 6b). Owned by
``parallax.conformance`` for the same reason ``story_models`` is: ``graph_stories.py``
is a real dev-only package module (its snippets render into the Usage Guide via
``gen-usage-guide``, which runs outside pytest entirely), so it needs classes
resolvable at ordinary import time, not only under pytest's test-path magic.
This module deliberately avoids ``from __future__ import annotations`` so the
metaclass reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

import datetime as dt
from decimal import Decimal

from parallax.core import (
    AsOfAxisMetadata,
    Attr,
    Entity,
    EntityConfig,
    Field,
    Rel,
    Relationship,
    RelationshipJoin,
    RelationshipTarget,
    ReverseRelationship,
)

_NS = "parallax.compatibility"

__all__ = ["Claim", "Coverage", "Policy"]

_AS_OF = (
    AsOfAxisMetadata(
        dimension="validTime", start_attribute="valid_start", end_attribute="valid_end"
    ),
    AsOfAxisMetadata(
        dimension="transactionTime", start_attribute="tx_start", end_attribute="tx_end"
    ),
)


class Policy(Entity, frozen=True):
    """Mirror of ``models/policy.yaml`` ``Policy`` (bitemporal, root of the
    ``coverages`` to-many relationship)."""

    __parallax__ = EntityConfig(
        table="policy", namespace=_NS, mutability="transactional", as_of=_AS_OF
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    valid_start: Attr[dt.datetime] = Field(name="valid_start", column="from_z")
    valid_end: Attr[dt.datetime] = Field(name="valid_end", column="thru_z")
    tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
    tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")
    coverages: Rel[tuple["Coverage", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Coverage", attribute="policyId")
        ),
        dependent=True,
    )


class Coverage(Entity, frozen=True):
    """Mirror of ``models/policy.yaml`` ``Coverage`` (bitemporal; the
    temporal navigate hop ``Policy.coverages`` reaches)."""

    __parallax__ = EntityConfig(
        table="coverage", namespace=_NS, mutability="transactional", as_of=_AS_OF
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    policy_id: Attr[int] = Field(column="policy_id", type="int64")
    amount: Attr[Decimal] = Field(type="decimal(18,2)")
    valid_start: Attr[dt.datetime] = Field(name="valid_start", column="from_z")
    valid_end: Attr[dt.datetime] = Field(name="valid_end", column="thru_z")
    tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
    tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")
    claims: Rel[tuple["Claim", ...]] = Relationship(
        cardinality="one-to-many",
        join=RelationshipJoin(
            source="id", target=RelationshipTarget(entity="Claim", attribute="coverageId")
        ),
        dependent=True,
    )
    policy: Rel["Policy"] = ReverseRelationship(reverse_of="Policy.coverages")


class Claim(Entity, frozen=True):
    """Mirror of ``models/policy.yaml`` ``Claim`` (bitemporal leaf, no
    relationships of its own)."""

    __parallax__ = EntityConfig(
        table="claim", namespace=_NS, mutability="transactional", as_of=_AS_OF
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    coverage_id: Attr[int] = Field(column="coverage_id", type="int64")
    reserve: Attr[Decimal] = Field(type="decimal(18,2)")
    valid_start: Attr[dt.datetime] = Field(name="valid_start", column="from_z")
    valid_end: Attr[dt.datetime] = Field(name="valid_end", column="thru_z")
    tx_start: Attr[dt.datetime] = Field(name="tx_start", column="in_z")
    tx_end: Attr[dt.datetime] = Field(name="tx_end", column="out_z")
