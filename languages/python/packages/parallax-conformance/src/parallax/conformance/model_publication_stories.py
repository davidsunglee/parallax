"""``parallax.conformance.model_publication_stories`` — the executable API-suite
story for updating a running service's model (`python.md` §2, ADR 0062).

Every other artifact states one fact of publication in isolation: that a
candidate is prepared whole, that a compare-and-replace is atomic, that an
execution retains what it adopted. What none of them states is the ORDER a host
must put those facts in, which is the whole of what an application owns here —
prepare the candidate first, because that is where every fallible derivation
runs; apply the schema next, because publication asserts the schema already
satisfies what it publishes; publish last, because nothing may adopt an edition
the database cannot answer for.

That order is the story, and it is what
``tests/api/test_model_publication_story.py`` executes against real Postgres, so
the documented spelling of an update cannot drift from a working one.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from parallax.conformance.models import accepted_model_of
from parallax.conformance.story_models import (
    ACCOUNT_MODEL,
    NICKNAMED_ACCOUNT_MODEL,
    NicknamedAccount,
)
from parallax.core.db_port import BeginFailed, Committed, DbPort
from parallax.evolution import (
    Evolution,
    SchemaDelta,
    UnilateralEvolution,
    evolve,
    schema_delta,
)
from parallax.snapshot import ServingModel, connect, prepare_model
from parallax.snapshot.handle import Transaction

__all__ = [
    "PublishedUpdate",
    "UnpublishableUpdateError",
    "a_running_service_publishes_an_evolved_model_without_restarting",
    "apply_schema_delta",
    "publication_snippet",
    "unilateral",
]

_TARGET_ID = 2
_NICKNAME = "rainy-day"


class UnpublishableUpdateError(Exception):
    """The application's own refusal to publish: the update stops before it.

    Application-owned rather than borrowed from the framework, because every
    reason it is raised for is the application's: which evolutions it is willing
    to apply live, and what it makes of a schema statement that did not commit.
    Parallax refuses nothing here — it never inspects a schema and never applies
    one — so an update that must not proceed has to say so in the host's own
    vocabulary. Whenever it is raised, the earlier selection is still serving and
    nothing has adopted the candidate.
    """


def unilateral(evolution: Evolution, /) -> UnilateralEvolution:
    """``evolution`` as the only kind a live publication can carry, or refuse.

    A Coordinated Evolution is a complete description whose application needs
    authored changes, data transformation, or rollout coordination, so there is
    no delta to apply and no moment at which one publication would make the two
    editions agree. Refusing it here is what keeps that decision the
    application's rather than something a generated statement discovers.
    """
    if isinstance(evolution, UnilateralEvolution):
        return evolution
    raise UnpublishableUpdateError(
        "a Coordinated Evolution needs authored, data, or rollout work that no "
        "single publication can stand in for"
    )


def apply_schema_delta(port: DbPort, delta: SchemaDelta, /) -> None:
    """Apply every statement of ``delta``, in order, in the host's OWN boundary.

    Parallax applies no schema change: these statements are the application's to
    run, on the connection it owns, before it publishes anything. They are
    prefix-safe in this order and deliberately not idempotent, so a run that
    stops partway leaves a database the earlier edition still operates against —
    which is exactly why a failure here has to prevent the publication rather
    than be reported beside it.
    """
    outcome = port.transaction(
        lambda schema: [schema.execute_write(statement, ()) for statement in delta.statements]
    )
    if isinstance(outcome, Committed):
        return
    failed = outcome.error if isinstance(outcome, BeginFailed) else outcome.trigger.error
    raise UnpublishableUpdateError("the schema delta did not apply in full") from failed


@dataclass(frozen=True, slots=True)
class PublishedUpdate:
    """What one live update did: the editions either side of it, the statements
    the host applied between them, and the added member's first written value."""

    before: str
    statements: tuple[str, ...]
    after: str
    nickname: str | None


def a_running_service_publishes_an_evolved_model_without_restarting(
    port: DbPort, /
) -> PublishedUpdate:
    """Prepare, apply, publish — in that order — with the service still serving.

    ``port`` is the shipped adapter over the story database, already carrying
    the earlier edition's schema. The handle is connected once, before the
    update, and never reconnected: what changes under it is the selection its
    executions adopt, which is what "without restarting" means here.
    """
    serving = ServingModel(prepare_model(ACCOUNT_MODEL, edition="2026-09-a"))
    db = connect(port, serving)
    before = db.transact(lambda tx: tx.edition)

    a = serving.current()
    # Preparation is where every fallible model-only derivation runs, and it
    # runs BEFORE any schema work. A candidate that cannot be prepared raises
    # here, with the database untouched and `a` still the selection every
    # execution adopts.
    b = prepare_model(NICKNAMED_ACCOUNT_MODEL, edition="2026-09-b")

    # An Evolution is described between two ACCEPTED models, which is what a
    # prepared selection carries its own of: `accepted_model_of` is the durable
    # first-party seam a schema-owning host reads one through (`python.md` §2).
    evolution = unilateral(evolve(accepted_model_of(a.model), accepted_model_of(b.model)))
    delta = schema_delta(evolution, port.dialect)
    apply_schema_delta(port, delta)

    # Only now. Publication ASSERTS that the physical schema already satisfies
    # what is being published, so every execution that adopts B afterwards finds
    # the column B was prepared over. `expected=a` is what makes this one step
    # rather than a read and a write: a publisher that lost a race to another
    # candidate is refused here with `PublicationConflictError` instead of
    # overwriting the winner.
    serving.publish(b, expected=a)

    def name_the_account(tx: Transaction) -> tuple[str, str | None]:
        account = tx.find(NicknamedAccount.where(NicknamedAccount.id == _TARGET_ID)).result()
        named = account.edit(nickname=_NICKNAME)
        tx.update(named)
        return tx.edition, named.nickname

    after, nickname = db.transact(name_the_account)
    return PublishedUpdate(
        before=before, statements=delta.statements, after=after, nickname=nickname
    )


def publication_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift.

    The later model, the application's own refusal, what one update answers,
    and the update itself: a snippet showing the three calls alone would
    document the surface without the order that is the only thing an
    application has to get right.
    """
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            NicknamedAccount,
            UnpublishableUpdateError,
            unilateral,
            apply_schema_delta,
            PublishedUpdate,
            a_running_service_publishes_an_evolved_model_without_restarting,
        )
    )
