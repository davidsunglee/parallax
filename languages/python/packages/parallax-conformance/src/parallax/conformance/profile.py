"""``parallax.conformance.profile`` — the declared matrix profiles (spec §6).

A profile is one named database-backed recipe: the provisioner that opens the
adapter the suite executes against. It authors no dialect of its own — the
adapter already declares the one it executes in (`m-db-port`), so a profile reads
that back off class-level metadata and a profile naming a dialect its adapter
does not execute in is unrepresentable rather than merely wrong. Resolving a
profile, and reading its dialect, opens no container and no connection: the reach
to the concrete adapter is deferred inside the provisioner, keeping the driver out
of every import graph that only needs to answer which SQL a profile is spelled in.

A profile also constitutes its own runs. :class:`ProfileRun` pairs the name a run
reports under with the port it executes through, and a profile is what makes one,
so a run reported under one profile beside a database another opened has no
spelling here rather than being caught after the fact
(`database-provider-test-contract.md`).
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final

from parallax.conformance.provision import Provisioner
from parallax.core.db_port import (
    DbPort,
    DeclaresDialect,
    DocumentReadOrdinals,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import Dialect
from parallax.core.metamodel import Metamodel

__all__ = [
    "PROFILES",
    "Profile",
    "ProfileRun",
    "ProvisionedRun",
    "profile_dialects",
    "profile_for",
]


class _NoProvisioningPort:
    """A `DbPort` that raises if touched — the structural proof that a
    `rejected`-shape ``run`` never provisions and never executes SQL
    (m-conformance-adapter): such a run is dispatched with THIS port instead of a
    Docker-backed one, so a future regression that makes the rejected lane reach
    the port fails loudly rather than silently starting a container.

    It lives beside the profile because the profile is what constitutes a run of
    itself: the provisioning-free lane is one of the ways a profile is run, not a
    detail of the command surface that asks for it.

    It still reports a dialect, because what it refuses is executing SQL rather
    than answering metadata: the run it stands in for names the dialect its
    rejection is classified under, and reading that off a port must not depend
    on the port being usable.
    """

    def __init__(self, dialect: Dialect) -> None:
        self.dialect = dialect

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:  # pragma: no cover
        del binds, document_reads
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:  # pragma: no cover
        raise AssertionError(f"a rejected-case run must not execute SQL: {sql!r}")

    def transaction[T](
        self, body: Callable[[DbPort], T], *, isolation: str | None = None
    ) -> TransactionOutcome[T]:  # pragma: no cover
        raise AssertionError("a rejected-case run must not open a transaction")


@dataclass(frozen=True, slots=True)
class ProfileRun:
    """One run of a declared profile: the name it reports under, and the port the
    case executes through.

    One value rather than two arguments because a name and a port passed apart can
    disagree — a run reported under one profile while another's database executed
    it is a well-formed and false report, and two profiles sharing a dialect leave
    nothing in the report to notice it. So the pair is constructed rather than
    checked: :meth:`Profile.provisioned`, :meth:`Profile.unprovisioned`, and
    :meth:`Profile.on_stand_in` are the only ways to make one, and each names the
    profile whose port it holds.

    It answers no dialect of its own. What executes spells its own SQL, so the
    dialect a run is graded and reported in is read off ``port`` alone (`m-dialect`).
    """

    name: str
    port: DbPort


@dataclass(frozen=True, slots=True)
class ProvisionedRun(ProfileRun):  # pragma: no cover - exercised by the Docker-backed lanes
    """A :class:`ProfileRun` over a database the profile provisioned for it.

    Preparing that database is part of running a case, so the provider operations
    a run needs are delegated here rather than the provisioner being handed out:
    a caller that could take the recipe back out could open a second database and
    pair it with a different profile's name, which is the arrangement
    :class:`ProfileRun` exists to make unspellable.
    """

    _provisioner: Provisioner

    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures."""
        self._provisioner.reset(model, fixtures)

    def peer(self, *, autocommit: bool = True) -> DbPort:
        """An independent second connection to the same database (provider `peer`)."""
        return self._provisioner.peer(autocommit=autocommit)


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

    @contextmanager
    def provisioned(self) -> Generator[ProvisionedRun]:  # pragma: no cover - Docker
        """Open this profile's declared provisioning and yield the run over the port
        it opened, closing the provisioner on exit.

        This is how a database-backed run is constituted: the caller names a
        profile and never a port, so the name the envelope reports and the database
        that produced it are the same declaration by construction.
        """
        provisioner = self.provisioner()
        try:
            yield ProvisionedRun(self.name, provisioner.port, provisioner)
        finally:
            provisioner.close()

    def unprovisioned(self) -> ProfileRun:
        """This profile's run of a case whose answer needs no database.

        A `rejected`-shape case is provisioning-free by contract
        (m-conformance-adapter): its answer is the classified rule, touching no
        SQL. The run therefore executes through a port that refuses SQL and answers
        only this profile's dialect, which is what the refusal is classified and
        reported under.
        """
        return ProfileRun(self.name, _NoProvisioningPort(self.dialect))

    def on_stand_in(self, port: DbPort) -> ProfileRun:
        """This profile's run over *port* — the one way to build a run whose
        database this profile did not open.

        It exists for the callers that stand a double in for a database: unit tests
        driving the adapter core through a scripted port, and the Docker-free
        sweeps. Those grade an envelope they construct and inspect in one process;
        none publishes one as a result of running the matrix, so nothing here can
        attribute a real run to the wrong profile. Every caller that does publish
        one reaches a run through :meth:`provisioned` or :meth:`unprovisioned` and
        names no port at all.
        """
        return ProfileRun(self.name, port)


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
