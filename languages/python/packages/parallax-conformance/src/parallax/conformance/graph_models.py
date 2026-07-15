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

from parallax.core import AsOfAttribute, Attr, Entity, EntityConfig, Field, Rel, Relationship

_NS = "parallax.compatibility"

__all__ = ["Claim", "Coverage", "Policy"]

_AS_OF = (
    AsOfAttribute(name="businessDate", from_column="from_z", to_column="thru_z", axis="business"),
    AsOfAttribute(name="processingDate", from_column="in_z", to_column="out_z", axis="processing"),
)


class Policy(Entity, frozen=True):
    """Mirror of ``models/policy.yaml`` ``Policy`` (bitemporal, root of the
    ``coverages`` to-many relationship)."""

    __parallax__ = EntityConfig(
        table="policy", namespace=_NS, mutability="transactional", as_of=_AS_OF
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    name: Attr[str] = Field(max_length=64)
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")
    coverages: Rel[tuple["Coverage", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Coverage.policyId",
        related_entity="Coverage",
        reverse_name="policy",
        dependent=True,
        foreign_key="policy_id",
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
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")
    claims: Rel[tuple["Claim", ...]] = Relationship(
        cardinality="one-to-many",
        join="this.id = Claim.coverageId",
        related_entity="Claim",
        reverse_name="coverage",
        dependent=True,
        foreign_key="coverage_id",
    )
    policy: Rel["Policy"] = Relationship(
        cardinality="many-to-one",
        join="this.policyId = Policy.id",
        related_entity="Policy",
        reverse_name="coverages",
        foreign_key="policy_id",
    )


class Claim(Entity, frozen=True):
    """Mirror of ``models/policy.yaml`` ``Claim`` (bitemporal leaf, no
    relationships of its own)."""

    __parallax__ = EntityConfig(
        table="claim", namespace=_NS, mutability="transactional", as_of=_AS_OF
    )

    id: Attr[int] = Field(primary_key=True, pk_generator="none", type="int64")
    coverage_id: Attr[int] = Field(column="coverage_id", type="int64")
    reserve: Attr[Decimal] = Field(type="decimal(18,2)")
    business_from: Attr[dt.datetime] = Field(column="from_z")
    business_to: Attr[dt.datetime] = Field(column="thru_z")
    processing_from: Attr[dt.datetime] = Field(column="in_z")
    processing_to: Attr[dt.datetime] = Field(column="out_z")
