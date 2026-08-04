"""The closed ``EntityDefinitionError`` code set.

Two things are pinned here: that the vocabulary is exactly the eleven codes
Python spec §2 declares, and that every rejection the frontend probes trigger
draws its code from that set. Adding a rejection without declaring its code, or
declaring a code no rule raises, fails one of the two.
"""

from __future__ import annotations

from typing import cast

import pytest

from _support import frontend_probes, frontend_probes_stringized
from parallax.core.entity import ENTITY_DEFINITION_CODES, EntityDefinitionError

_SPEC_CODES = frozenset(
    {
        "entity-header-unknown-option",
        "entity-header-invalid-value",
        "entity-header-missing-option",
        "entity-base-invalid",
        "entity-annotation-invalid",
        "entity-member-value-invalid",
        "entity-option-invalid-value",
        "entity-option-context-invalid",
        "entity-reserved-member-name",
        "entity-canonical-name-collision",
        "entity-relationship-annotation-mismatch",
    }
)

# Every class-creation and factory-call rejection, paired with the code it must
# raise. `entity-relationship-annotation-mismatch` is absent because it is the
# one code raised during `DomainModel` construction rather than at class creation.
_PROBES: dict[str, str] = {
    "define_header_unknown_option": "entity-header-unknown-option",
    "define_header_invalid_value": "entity-header-invalid-value",
    "define_inheritance_invalid_strategy": "entity-header-invalid-value",
    "define_header_missing_option": "entity-header-missing-option",
    "define_base_invalid": "entity-base-invalid",
    "define_annotation_invalid": "entity-annotation-invalid",
    "define_annotation_unmapped_type": "entity-annotation-invalid",
    "define_member_value_invalid": "entity-member-value-invalid",
    "define_relationship_without_rel": "entity-member-value-invalid",
    "define_option_invalid_value": "entity-option-invalid-value",
    "define_empty_index": "entity-option-context-invalid",
    "define_mixed_rel_forms": "entity-option-context-invalid",
    "define_option_context_invalid": "entity-option-context-invalid",
    "define_decimal_without_precision": "entity-option-context-invalid",
    "define_narrowing_on_wrong_family": "entity-option-context-invalid",
    "define_reserved_member_name": "entity-reserved-member-name",
    "define_reserved_query_root_name": "entity-reserved-member-name",
    "define_reserved_temporal_name": "entity-reserved-member-name",
    "define_reserved_canonical_temporal_name": "entity-reserved-member-name",
    "define_reserved_temporal_name_by_rename": "entity-reserved-member-name",
    "define_class_var_reserved_name": "entity-reserved-member-name",
    "define_shadowed_declaration_member": "entity-reserved-member-name",
    "define_nullable_many_relationship": "entity-annotation-invalid",
    "define_wide_union_annotation": "entity-annotation-invalid",
    "define_wide_union_relationship_target": "entity-annotation-invalid",
    "define_canonical_name_collision": "entity-canonical-name-collision",
}

_MODULES = {"live": frontend_probes, "stringized": frontend_probes_stringized}


def test_the_declared_code_set_is_exactly_the_eleven_spec_codes() -> None:
    assert ENTITY_DEFINITION_CODES == _SPEC_CODES
    assert len(ENTITY_DEFINITION_CODES) == 11


def test_a_code_outside_the_closed_set_cannot_be_raised() -> None:
    with pytest.raises(ValueError, match="not an entity definition code"):
        EntityDefinitionError(code="entity-made-up", message="nope")


@pytest.mark.parametrize("path", sorted(_MODULES))
@pytest.mark.parametrize("probe", sorted(_PROBES))
def test_every_probe_raises_its_declared_code(path: str, probe: str) -> None:
    define = cast("object", getattr(_MODULES[path], probe))
    assert callable(define)
    with pytest.raises(EntityDefinitionError) as caught:
        define()
    assert caught.value.code == _PROBES[probe]
    assert caught.value.code in ENTITY_DEFINITION_CODES


def test_every_probe_covers_a_declared_code_and_only_realization_is_unprobed() -> None:
    probed = set(_PROBES.values())
    assert probed <= ENTITY_DEFINITION_CODES
    assert ENTITY_DEFINITION_CODES - probed == {"entity-relationship-annotation-mismatch"}
