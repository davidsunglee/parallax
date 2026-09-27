from __future__ import annotations

from collections.abc import Iterable, Sequence

from parallax.core.metamodel import EntityIdentity

__all__ = ["declaration_order"]


def declaration_order(
    chains: Sequence[Sequence[EntityIdentity]],
    family: Iterable[EntityIdentity] = (),
    root: EntityIdentity | None = None,
) -> tuple[tuple[EntityIdentity, ...], int]:
    """The contributor order of a family declaration stream, and its prefix length.

    ``chains`` holds each effective concrete's root-first ancestry, in canonical
    concrete order. Ancestors contribute first, each at its first encounter
    while traversing those chains; then the concretes contribute in canonical
    order. That prefix is the projection over the effective set. Every
    ``family`` participant not yet encountered then follows, ``root`` first and
    the rest in canonical Entity Identity order, so a dormant child can precede
    its dormant parent.

    The concretes are encountered before any ancestor is visited, so a concrete
    that is also another chain's ancestor contributes once, at its concrete
    position.
    """
    encountered = {chain[-1] for chain in chains}
    contributors: list[EntityIdentity] = []
    for chain in chains:
        for ancestor in chain[:-1]:
            if ancestor in encountered:
                continue
            encountered.add(ancestor)
            contributors.append(ancestor)
    contributors.extend(chain[-1] for chain in chains)
    prefix = len(contributors)
    for participant in sorted(family, key=lambda member: (member != root, member.sort_key)):
        if participant in encountered:
            continue
        encountered.add(participant)
        contributors.append(participant)
    return tuple(contributors), prefix
