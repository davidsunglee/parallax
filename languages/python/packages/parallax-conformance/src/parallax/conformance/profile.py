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
reports under with the port it executes through, and it is constructed from a
profile rather than from a name, so the pairing is made by the profile instead of
checked after the fact (`database-provider-test-contract.md`). The lanes that
publish a run name no port at all: the profile opens it.
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


@dataclass(frozen=True, slots=True, init=False)
class ProfileRun:
    """One run of a declared profile: the name it reports under, and the port the
    case executes through.

    One value rather than two arguments because a name and a port passed apart can
    disagree — a run reported under one profile while another's database executed
    it is a well-formed and false report, and two profiles sharing a dialect leave
    nothing in the report to notice it. So a reporting name is not spellable beside
    a port: this takes the profile itself and reads the name off it, and a run
    reported under a name no profile answers to has no spelling here. A profile's
    own runs — the ones a published envelope comes from — are
    :meth:`Profile.provisioned` and :meth:`Profile.unprovisioned`, which name no
    port at all. Pairing a profile with a port it did not open is what this
    constructor does, and :meth:`Profile.on_stand_in` is its spelling at the call
    sites that need it, which say so by using it.

    It answers no dialect of its own. What executes spells its own SQL, so the
    dialect a run is graded and reported in is read off ``port`` alone (`m-dialect`).
    """

    name: str
    port: DbPort

    def __init__(self, profile: Profile, port: DbPort) -> None:
        object.__setattr__(self, "name", profile.name)
        object.__setattr__(self, "port", port)


@dataclass(frozen=True, slots=True, init=False)
class ProvisionedRun(ProfileRun):
    """A :class:`ProfileRun` over a database the profile provisioned for it.

    It takes the open provisioner and reads the port off it rather than being
    handed the two, so the database this run reports through is the one this
    provisioner opened.

    Preparing that database is part of running a case, so the provider operations
    a run needs are delegated here rather than the provisioner being handed out:
    handing the recipe back out would give a caller that needs only the database
    this run holds the means to open a second one.
    """

    _provisioner: Provisioner

    def __init__(self, profile: Profile, provisioner: Provisioner) -> None:
        ProfileRun.__init__(self, profile, provisioner.port)
        object.__setattr__(self, "_provisioner", provisioner)

    def reset(  # pragma: no cover - exercised by the Docker-backed lanes
        self, model: Metamodel, fixtures: Mapping[str, object]
    ) -> None:
        """Reset the schema, apply the model-derived DDL, and load the fixtures."""
        self._provisioner.reset(model, fixtures)

    def peer(self, *, autocommit: bool = True) -> DbPort:  # pragma: no cover - Docker
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
            yield ProvisionedRun(self, provisioner)
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
        return ProfileRun(self, _NoProvisioningPort(self.dialect))

    def on_stand_in(self, port: DbPort) -> ProfileRun:
        """This profile's run over *port* — a run whose database this profile did
        not open, named at the call site as the substitution it is.

        It exists for the callers that stand a double in for a database: unit tests
        driving the adapter core through a scripted port, and the Docker-free
        sweeps. Those grade an envelope they construct and inspect in one process;
        none publishes one as a result of running the matrix, so nothing here can
        attribute a real run to the wrong profile. Every caller that does publish
        one reaches a run through :meth:`provisioned` or :meth:`unprovisioned` and
        names no port at all.
        """
        return ProfileRun(self, port)


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
