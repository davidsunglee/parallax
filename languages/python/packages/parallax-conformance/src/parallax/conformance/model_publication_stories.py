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

from parallax.conformance.story_models import (
    ACCOUNT_MODEL,
    NICKNAMED_ACCOUNT_MODEL,
    Account,
    NicknamedAccount,
)
from parallax.core.db_port import (
    BeginFailed,
    Committed,
    DbPort,
    RollbackFailed,
    RolledBack,
)
from parallax.core.entity import model_of
from parallax.evolution import (
    CreatedIndex,
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
    vocabulary. Raised at either step this recipe puts BEFORE its publication,
    so under this order the earlier selection is still serving and nothing has
    adopted the candidate.

    ``triggering_error`` and ``rollback_error`` are both live objects when an
    undo did not complete, because either alone misreports what happened; each
    is ``None`` where only one failure is live, and that one is the ``__cause__``.
    """

    def __init__(
        self,
        message: str,
        /,
        *,
        triggering_error: BaseException | None = None,
        rollback_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.triggering_error = triggering_error
        self.rollback_error = rollback_error


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


def apply_schema_delta(port: DbPort, delta: SchemaDelta, /) -> tuple[CreatedIndex, ...]:
    """Apply every statement of ``delta``, in order, in the host's OWN boundary.

    Parallax applies no schema change: these statements are the application's to
    run, on the connection it owns, before it publishes anything. They are
    prefix-safe in this order and deliberately not idempotent, so a run that
    stops partway leaves a database the earlier edition still operates against —
    which is exactly why a failure here has to prevent the publication rather
    than be reported beside it.

    What comes back is the delta's own ``created_indices`` provenance, which the
    host keeps as its rollout ledger: it is what a later uniqueness violation is
    matched against, by the violated Physical Index Name the database error
    already carries, without parsing a driver message.
    """
    outcome = port.transaction(
        lambda schema: [schema.execute_write(statement, ()) for statement in delta.statements]
    )
    match outcome:
        case Committed():
            return delta.created_indices
        case BeginFailed(error):
            raise UnpublishableUpdateError("the schema delta never began") from error
        # A control-flow or fatal trigger — an interrupt, a cancellation — stays
        # primary at both rollback outcomes rather than being downgraded into an
        # ordinary refusal a host catches and reports as a failed update.
        case RolledBack(trigger) if not isinstance(trigger.error, Exception):
            raise trigger.error
        case RolledBack(trigger):
            raise UnpublishableUpdateError(
                "the schema delta did not apply in full"
            ) from trigger.error
        case RollbackFailed(trigger, rollback_error) if not isinstance(trigger.error, Exception):
            raise trigger.error from rollback_error
        case RollbackFailed(trigger, rollback_error):
            # Both failures are live and either alone misreports what happened:
            # the statements that had already succeeded could not be undone, so
            # WHICH prefix the database now holds is unknown and the connection
            # is no longer trustworthy. Retrying the delta is exactly what must
            # not happen — a prefix-safe statement is not an idempotent one.
            raise UnpublishableUpdateError(
                f"the schema delta could not be undone after {trigger.error!r}; the undo failed "
                f"with {rollback_error!r}, so how much of the delta the database holds is unknown",
                triggering_error=trigger.error,
                rollback_error=rollback_error,
            ) from rollback_error


@dataclass(frozen=True, slots=True)
class PublishedUpdate:
    before_edition: str
    statements: tuple[str, ...]
    created_indices: tuple[CreatedIndex, ...]
    after_edition: str
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
    # prepared selection carries its own of: `model_of` is the durable first-party
    # seam a schema-owning host reads one through (`python.md` §2).
    evolution = unilateral(evolve(model_of(a.model), model_of(b.model)))
    # The statements are applied exactly as given — never reordered,
    # deduplicated, or made idempotent — because a delta states what must happen
    # to a database at the earlier edition rather than reconciling an unknown one.
    delta = schema_delta(evolution, port.dialect)
    created_indices = apply_schema_delta(port, delta)

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
        before_edition=before,
        statements=delta.statements,
        created_indices=created_indices,
        after_edition=after,
        nickname=nickname,
    )


def publication_snippet() -> str:
    """The story's own source — the Usage Guide snippet that cannot drift.

    Both model endpoints, the application's own refusal, what one update
    answers, and the update itself: a snippet showing the three calls alone
    would document the surface without the order that is the only thing an
    application has to get right.
    """
    return "\n\n\n".join(
        inspect.getsource(part).rstrip("\n")
        for part in (
            Account,
            NicknamedAccount,
            UnpublishableUpdateError,
            unilateral,
            apply_schema_delta,
            PublishedUpdate,
            a_running_service_publishes_an_evolved_model_without_restarting,
        )
    )
