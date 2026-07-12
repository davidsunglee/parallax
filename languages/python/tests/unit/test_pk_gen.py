"""m-pk-gen: strategy classification and simulated-sequence block arithmetic."""

from __future__ import annotations

import pytest

from parallax.conformance import case_format
from parallax.conformance import models as corpus_models
from parallax.core import pk_gen
from parallax.core.descriptor import PkGenerator

pytestmark = pytest.mark.unit

_MODELS = corpus_models.load_models(
    case_format.find_repo_root() / "core" / "compatibility" / "models"
)


def test_generates_distinguishes_supplied_from_allocated_keys() -> None:
    assert pk_gen.generates(None) is False
    assert pk_gen.generates(PkGenerator(strategy="none")) is False
    assert pk_gen.generates(PkGenerator(strategy="max")) is True
    assert pk_gen.generates(PkGenerator(strategy="sequence", sequence_name="s")) is True


def test_generated_key_attribute_finds_the_max_pk() -> None:
    attendee = _MODELS["pk-max"].entity("Attendee")
    attr = pk_gen.generated_key_attribute(attendee)
    assert attr is not None
    assert attr.name == "id"


def test_generated_key_attribute_is_none_for_supplied_keys() -> None:
    account = _MODELS["account"].entity("Account")
    assert pk_gen.generated_key_attribute(account) is None


def test_resolve_sequence_fills_defaults() -> None:
    resolved = pk_gen.resolve_sequence(PkGenerator(strategy="sequence", sequence_name="s"))
    assert resolved == pk_gen.SequenceConfig("s", initial_value=1, increment_size=1, batch_size=1)


def test_resolve_sequence_rejects_non_sequence_and_missing_name() -> None:
    with pytest.raises(ValueError, match="not a sequence"):
        pk_gen.resolve_sequence(PkGenerator(strategy="max"))
    with pytest.raises(ValueError, match="sequenceName"):
        pk_gen.resolve_sequence(PkGenerator(strategy="sequence"))


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
    generators = {
        attr.pk_generator.sequence_name: attr.pk_generator
        for entity in _MODELS["pk-sequence"].entities
        for attr in entity.attributes
        if attr.pk_generator is not None and attr.pk_generator.strategy == "sequence"
    }
    config = pk_gen.resolve_sequence(generators[sequence_name])
    ids, new_next = pk_gen.allocate_block(config, config.initial_value)
    assert ids == expected_first_block
    assert new_next == expected_new_next


def test_allocate_block_is_contiguous_across_calls() -> None:
    config = pk_gen.SequenceConfig("s", initial_value=100, increment_size=10, batch_size=2)
    first, next_after_first = pk_gen.allocate_block(config, config.initial_value)
    second, _ = pk_gen.allocate_block(config, next_after_first)
    assert first == (100, 110)
    assert second == (120, 130)


def test_registry_role_names_are_stable() -> None:
    assert pk_gen.REGISTRY_KEY_ROLE == "sequenceName"
    assert pk_gen.REGISTRY_VALUE_ROLE == "nextValue"
