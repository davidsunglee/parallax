"""The closed ``EntityDefinitionCode`` vocabulary.

Every rejection the frontend probes trigger draws its code from that set, and
every code but the one raised during ``DomainModel`` construction has a probe.
Adding a rejection without declaring its code, or declaring a code no probe
raises, fails here.
"""

from __future__ import annotations

from typing import cast, get_args

import pytest

from parallax.core import UsageError
from parallax.core.entity._errors import EntityDefinitionCode
from tests._support import frontend_probes, frontend_probes_stringized
from tests._support.errors import raises_code

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
    "define_reserved_edit_verb_name": "entity-reserved-member-name",
    "define_shadowed_model_namespace_binding": "entity-reserved-member-name",
    "define_framework_slot_binding": "entity-reserved-member-name",
    "define_reserved_pickle_entry_name": "entity-reserved-member-name",
    "define_value_object_reserved_pickle_entry_name": "entity-reserved-member-name",
    "define_reserved_core_schema_hook_name": "entity-reserved-member-name",
    "define_value_object_reserved_core_schema_hook_name": "entity-reserved-member-name",
    "define_reserved_instance_state_name": "entity-reserved-member-name",
    "define_reserved_populated_members_name": "entity-reserved-member-name",
    "define_value_object_reserved_instance_state_name": "entity-reserved-member-name",
    "define_value_object_reserved_populated_members_name": "entity-reserved-member-name",
    "define_nullable_many_relationship": "entity-annotation-invalid",
    "define_wide_union_annotation": "entity-annotation-invalid",
    "define_wide_union_relationship_target": "entity-annotation-invalid",
    "define_canonical_name_collision": "entity-canonical-name-collision",
    "define_many_relationship_without_ellipsis": "entity-annotation-invalid",
    "define_inheritance_invalid_role": "entity-header-invalid-value",
    "define_rel_value_under_attr": "entity-member-value-invalid",
    "define_attr_value_under_rel": "entity-member-value-invalid",
    "define_value_object_base_invalid": "entity-base-invalid",
    "define_value_object_occurrence_with_scalar_type": "entity-option-context-invalid",
}

_DECLARED = frozenset(get_args(EntityDefinitionCode.__value__))

_MODULES = {"live": frontend_probes, "stringized": frontend_probes_stringized}


@pytest.mark.parametrize("path", sorted(_MODULES))
@pytest.mark.parametrize("probe", sorted(_PROBES))
def test_every_probe_raises_its_declared_code(path: str, probe: str) -> None:
    define = cast("object", getattr(_MODULES[path], probe))
    assert callable(define)
    with raises_code(UsageError, _PROBES[probe]):
        define()


def test_every_probe_covers_a_declared_code_and_only_realization_is_unprobed() -> None:
    probed = set(_PROBES.values())
    assert probed <= _DECLARED
    assert _DECLARED - probed == {"entity-relationship-annotation-mismatch"}
