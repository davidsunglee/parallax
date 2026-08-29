"""``parallax.conformance.profile`` — the declared matrix profiles (spec §6).

A profile is one named database-backed recipe: the provisioner that opens the
adapter the suite executes against. It authors no dialect of its own — the
adapter already declares the one it executes in (`m-db-port`), so a profile reads
that back off class-level metadata and a profile naming a dialect its adapter
does not execute in is unrepresentable rather than merely wrong. Resolving a
profile, and reading its dialect, opens no container and no connection: the reach
to the concrete adapter is deferred inside the provisioner, keeping the driver out
of every import graph that only needs to answer which SQL a profile is spelled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from parallax.conformance.provision import Provisioner
from parallax.core.db_port import DeclaresDialect
from parallax.core.dialect import Dialect

__all__ = ["PROFILES", "Profile", "profile_dialects", "profile_for"]


@dataclass(frozen=True, slots=True)
class Profile:
    """One declared profile. ``name`` is its stable reporting name — the label a
    ``run`` envelope carries and a command surface selects it by."""

    name: str
    provisioner: type[Provisioner]

    @property
    def adapter(self) -> type[DeclaresDialect]:
        return self.provisioner.adapter()

    @property
    def dialect(self) -> Dialect:
        return self.adapter.dialect


PROFILES: Final[tuple[Profile, ...]] = (Profile("pg-full", Provisioner),)


def profile_for(name: str) -> Profile:
    """The declared profile named ``name``, or ``ValueError`` if none is.

    Selection by name from the one declared set — following ``dialect_for`` — so
    adding a profile is a visible edit and nothing registers itself.
    """
    for profile in PROFILES:
        if profile.name == name:
            return profile
    raise ValueError(f"unknown profile {name!r}")


def profile_dialects() -> tuple[str, ...]:
    """Every dialect some declared profile runs the claimed suite against, sorted
    and without repeats — profiles may share one."""
    return tuple(sorted({profile.dialect.name for profile in PROFILES}))
