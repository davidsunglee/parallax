"""Idiomatic Entity Classes the API-suite graph stories build statements over.

A mirror of ``models/policy.yaml`` (``Policy`` / ``Coverage`` / ``Claim``,
bitemporal entities that also relate), composed into the one sealed hub named for
that model. Owned by ``parallax.conformance`` for the same reason
``story_models`` is: ``graph_stories.py`` is a real dev-only package module (its
snippets render into the Usage Guide via ``gen-usage-guide``, which runs outside
pytest entirely), so it needs classes resolvable at ordinary import time.

This module deliberately avoids ``from __future__ import annotations`` so the
engine reads the live ``Attr[T]`` / ``Rel[T]`` objects directly.
"""

from decimal import Decimal

from parallax.core import (
    ONE_TO_MANY,
    Attr,
    Bitemporal,
    DomainModel,
    Rel,
    attr,
    index,
    rel,
)

_NS = "parallax.compatibility"

__all__ = ["POLICY_MODEL", "Claim", "Coverage", "Policy"]


class Policy(
    Bitemporal,
    table="policy",
    namespace=_NS,
    indices=(index("policy_pk", "id", "valid_start", "tx_start", unique=True),),
):
    """Mirror of ``models/policy.yaml`` ``Policy`` (bitemporal, root of the
    ``coverages`` to-many relationship)."""

    id: Attr[int] = attr(primary_key=True)
    name: Attr[str] = attr(max_length=64)
    coverages: Rel[tuple["Coverage", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "policy_id"), dependent=True
    )


class Coverage(
    Bitemporal,
    table="coverage",
    namespace=_NS,
    indices=(
        index("coverage_pk", "id", "valid_start", "tx_start", unique=True),
        index("coverage_policy", "policy_id"),
    ),
):
    """Mirror of ``models/policy.yaml`` ``Coverage`` (bitemporal; the temporal
    navigate hop ``Policy.coverages`` reaches)."""

    id: Attr[int] = attr(primary_key=True)
    policy_id: Attr[int]
    amount: Attr[Decimal] = attr(precision=18, scale=2)
    claims: Rel[tuple["Claim", ...]] = rel(
        cardinality=ONE_TO_MANY, join=("id", "coverage_id"), dependent=True
    )
    policy: Rel[Policy | None] = rel(reverse_of="coverages")


class Claim(
    Bitemporal,
    table="claim",
    namespace=_NS,
    indices=(
        index("claim_pk", "id", "valid_start", "tx_start", unique=True),
        index("claim_coverage", "coverage_id"),
    ),
):
    """Mirror of ``models/policy.yaml`` ``Claim`` (bitemporal leaf, no
    relationships of its own)."""

    id: Attr[int] = attr(primary_key=True)
    coverage_id: Attr[int]
    reserve: Attr[Decimal] = attr(precision=18, scale=2)


POLICY_MODEL = DomainModel(Policy, Coverage, Claim)
