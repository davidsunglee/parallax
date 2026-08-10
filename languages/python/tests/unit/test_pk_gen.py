"""m-pk-gen: strategy classification and simulated-sequence block arithmetic."""

from __future__ import annotations

import pytest
from _sql_gen_support import model as corpus_model

from parallax.core import pk_gen
from parallax.core.metamodel import (
    APPLICATION_ASSIGNED,
    MAX,
    EntityIdentity,
    Metamodel,
    PrimaryKey,
    Sequence,
)


def _model(stem: str) -> Metamodel:
    return corpus_model(stem)


def test_generates_distinguishes_supplied_from_allocated_keys() -> None:
    assert pk_gen.generates(APPLICATION_ASSIGNED) is False
    assert pk_gen.generates(MAX) is True
    assert pk_gen.generates(Sequence(name="s")) is True


def test_generated_key_attribute_finds_the_max_pk() -> None:
    attendee = _model("pk-max").entity(EntityIdentity("parallax.compatibility", "Attendee"))
    assert attendee is not None
    attribute = pk_gen.generated_key_attribute(attendee)
    assert attribute is not None
    assert attribute.identity.name == "id"


def test_generated_key_attribute_is_none_for_supplied_keys() -> None:
    account = _model("account").entity(EntityIdentity("parallax.compatibility", "Account"))
    assert account is not None
    assert pk_gen.generated_key_attribute(account) is None


def test_a_sequence_reaches_this_scope_with_every_default_resolved() -> None:
    # Acceptance fills an omitted sizing parameter, so the scope reads the
    # configuration off the accepted value rather than re-defaulting it.
    badge = _model("pk-sequence").entity(EntityIdentity("parallax.compatibility", "Badge"))
    assert badge is not None
    generated = pk_gen.generated_key_attribute(badge)
    assert generated is not None
    key = generated.primary_key
    assert isinstance(key, PrimaryKey)
    assert key.generation == Sequence(
        name="badge_seq", batch_size=1, initial_value=1, increment_size=1
    )


@pytest.mark.parametrize(
    ("sequence_name", "expected_first_block", "expected_new_next"),
    [
        ("badge_seq", (1,), 2),
        ("ticket_seq", (1000,), 1005),
        ("pass_seq", (1, 2, 3), 4),
        ("voucher_seq", (100, 110), 120),
    ],
)
def test_allocate_block_matches_the_corpus_sequence_configs(
    sequence_name: str, expected_first_block: tuple[int, ...], expected_new_next: int
) -> None:
    sequences = {
        attribute.primary_key.generation.name: attribute.primary_key.generation
        for entity in _model("pk-sequence").entities
        for attribute in entity.declared_attributes
        if isinstance(attribute.primary_key, PrimaryKey)
        and isinstance(attribute.primary_key.generation, Sequence)
    }
    sequence = sequences[sequence_name]
    ids, new_next = pk_gen.allocate_block(sequence, sequence.initial_value)
    assert ids == expected_first_block
    assert new_next == expected_new_next


def test_allocate_block_is_contiguous_across_calls() -> None:
    sequence = Sequence(name="s", initial_value=100, increment_size=10, batch_size=2)
    first, next_after_first = pk_gen.allocate_block(sequence, sequence.initial_value)
    second, _ = pk_gen.allocate_block(sequence, next_after_first)
    assert first == (100, 110)
    assert second == (120, 130)


def test_registry_role_names_are_stable() -> None:
    assert pk_gen.REGISTRY_KEY_ROLE == "sequenceName"
    assert pk_gen.REGISTRY_VALUE_ROLE == "nextValue"
