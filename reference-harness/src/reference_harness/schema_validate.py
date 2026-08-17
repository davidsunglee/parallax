"""Schema validation: the schemas are valid, and every fixture conforms.

Run as a module against the compatibility tree::

    uv run python -m reference_harness.schema_validate ../core/compatibility

It performs m-case-format layer 1 statically (no database needed):

* **Meta-schema validation** — each core schema is itself a valid JSON Schema
  (Draft 2020-12).
* **Descriptor validation** — every model under ``models/`` validates against the
  metamodel schema.
* **Object Query validation** — every case's ``when.objectQuery`` (and each
  scenario/coherence step's own) validates against the Object Query schema, which
  reaches the Predicate and Subtype Selection grammars through it.
* **Case validation** — every case validates against the compatibility-case
  schema, and its referenced model + golden-SQL dialect keys are coherent. The
  model-aware case-authoring rules JSON Schema cannot express are asked here too,
  where the model is in hand and no executor has run yet: a buffered write's
  member honesty, and a scenario `mutate`'s own assignments
  (:func:`_validate_scenario_edit`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry

from .case import Entity
from .corpus_yaml import read_corpus_yaml
from .execution_validate import validate_execution
from .inheritance import Family, resolve_effective_definition, validate_family_defs
from .keyed_write_validate import (
    states_framework_marker,
    undeclared_row_members,
    validate_keyed_write,
)
from .metamodel import validate_index_identities
from .predicate_write_validate import (
    PredicateWriteValidationError,
    validate_predicate_write,
    validate_predicate_write_materialization,
)
from .query_references import collect_query_reference_classes
from .schemas import build_registry, load_schemas
from .storage_layout import validate_storage_layout
from .temporal_selection_validate import validate_temporal_selections
from .temporality import derive_temporal_structure
from .value_object_resolve import RejectionError
from .write_validate import assignment_violation, undeclared_members


class ValidationFailure(Exception):
    """Raised with a human-readable list of problems."""


def _load_yaml(path: Path) -> Any:
    return read_corpus_yaml(path)


def validation_error(
    instance: Any, schema: dict[str, Any], registry: Registry | None = None
) -> str | None:
    """Return the most relevant JSON Schema failure, or ``None`` when valid.

    *registry* resolves cross-file ``$ref``s (the case schema references the
    canonical write-instruction ``$defs``, and the case, query, and
    write-instruction schemas all reference the identity grammars); a bare
    validator cannot reach another file, so callers validating any of those
    schemas MUST pass it.
    """
    validator = (
        Draft202012Validator(schema, registry=registry)
        if registry is not None
        else Draft202012Validator(schema)
    )
    found = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    if not found:
        return None
    match = best_match(found)
    location = "/".join(str(p) for p in match.absolute_path) or "<root>"
    return f"at {location}: {match.message}"


def _validate(
    instance: Any,
    schema: dict[str, Any],
    label: str,
    errors: list[str],
    registry: Registry | None = None,
) -> None:
    problem = validation_error(instance, schema, registry)
    if problem is not None:
        errors.append(f"{label}: {problem}")


def _descriptor_entity_defs(descriptor: Any) -> list[dict[str, Any]]:
    """Lift a descriptor (single ``entity`` or ``entities`` list) to a flat list."""
    if not isinstance(descriptor, dict):
        return []
    if "entities" in descriptor:
        entities = descriptor.get("entities")
        return [d for d in entities if isinstance(d, dict)] if isinstance(entities, list) else []
    entity = descriptor.get("entity")
    return [entity] if isinstance(entity, dict) else []


# --- Object Query self-consistency (m-case-format; m-inheritance) ------------
#
# A query names the entity it targets in its own `target`; the class part of every
# queried-entity reference the query carries MUST be CONSISTENT with it. This is
# one document checked against itself rather than two sibling fields reconciled.
# It is FAMILY-AWARE (m-inheritance): a reference class is consistent when its
# effective concrete-subtype set is a subset of the target's — an abstract root
# names its whole family, an abstract subtype its concrete descendants, a concrete
# subtype itself. For a non-inheritance entity the effective set is the entity
# itself, so "subset" reduces to "equal". A navigation's INNER predicate resolves
# against the RELATED entity, so it is intentionally not descended into.


def _check_query_target(
    query: Any,
    family: Family | None,
    label: str,
    errors: list[str],
) -> None:
    """Assert every queried-entity reference class is family-consistent with ``target``."""
    if not isinstance(query, dict):
        return  # a malformed query is already a schema error
    target = query.get("target")
    if not isinstance(target, str):
        return
    classes: set[str] = set()
    collect_query_reference_classes(query, classes)

    def effective(name: str) -> set[str]:
        return set(family.effective_concrete_set(name)) if family is not None else {name}

    target_set = effective(target)
    inconsistent = sorted(cls for cls in classes if not (effective(cls) <= target_set))
    if inconsistent:
        errors.append(
            f"{label}: objectQuery target {target!r} is inconsistent with the "
            f"queried-entity reference class(es) {inconsistent}"
        )


def _check_object_query(
    query: Any,
    schema: dict[str, Any],
    family: Family | None,
    label: str,
    errors: list[str],
    registry: Registry | None = None,
    *,
    model_aware: bool = True,
    encodings: Any = None,
    encodings_label: str | None = None,
) -> None:
    """Validate one Object Query wherever a case carries one, plus its encodings.

    *model_aware* is ``False`` for a `rejected` case, which authors a query a
    model-aware rule refuses, so its own references are deliberately inconsistent
    with its target.
    """
    _validate(query, schema, label, errors, registry)
    if model_aware:
        _check_query_target(query, family, label, errors)
        errors.extend(
            f"{label}: {problem}" for problem in validate_temporal_selections(query, family)
        )
    if encodings_label is None:
        return
    for index, encoding in enumerate(encodings or []):
        _validate(encoding, schema, f"{encodings_label}[{index}]", errors, registry)


def _scenario_reference_sql_dialect_keys(
    step: dict[str, Any], label: str, errors: list[str]
) -> None:
    """Ensure a scenario read's dialect map covers its golden statement maps.

    This is the scenario-local counterpart to the runner's top-level
    ``then.referenceSql`` key check.  A plain string is dialect-neutral.  A map
    must cover exactly the dialects this read step can execute, otherwise one
    dialect would silently lose its independent oracle.
    """
    reference_sql = step.get("referenceSql")
    if not isinstance(reference_sql, dict):
        return
    statements = step.get("statements")
    if not isinstance(statements, list) or not statements:
        return
    dialect_sets = [
        set(entry["sql"])
        for entry in statements
        if isinstance(entry, dict) and isinstance(entry.get("sql"), dict)
    ]
    if not dialect_sets:
        return
    golden_dialects = set.intersection(*dialect_sets)
    if set(reference_sql) != golden_dialects:
        errors.append(
            f"{label}: referenceSql map keys {sorted(reference_sql)} != scenario golden sql "
            f"map keys {sorted(golden_dialects)}"
        )


def _validate_predicate_write(
    write: Any,
    entity_defs: list[dict[str, Any]],
    predicate_schema: dict[str, Any],
    label: str,
    errors: list[str],
    registry: Registry | None = None,
) -> Entity | None:
    """Validate the predicate and model-dependent parts of one write instruction."""
    if not isinstance(write, dict):
        return None  # legacy string writes remain valid and need no predicate walk
    target = write.get("target")
    if not isinstance(target, dict):
        return None  # the case schema owns missing/malformed target errors
    predicate = target.get("predicate")
    if predicate is not None:
        _validate(predicate, predicate_schema, f"{label} target.predicate", errors, registry)
    target_name = target.get("entity")
    if not isinstance(target_name, str):
        return None
    try:
        entity = Entity(definition=resolve_effective_definition(entity_defs, target_name))
    except (KeyError, RejectionError) as exc:
        errors.append(f"{label}: target entity {target_name!r} is not declared: {exc}")
        return None
    try:
        validate_predicate_write(entity, write)
    except PredicateWriteValidationError as exc:
        errors.append(f"{label}: {exc}")
    return entity


def _effective_entity(entity_defs: list[dict[str, Any]], entity_name: str) -> Entity | None:
    """*entity_name*'s effective definition, or ``None`` when it is undeclared.

    A descendant declares no temporality of its own and inherits the root's
    profile unchanged (`m-inheritance`), so every model-aware judgement about a
    keyed entry reads the effective definition rather than the entity's own
    declaration — a concrete temporal subtype is temporal here even though it
    declares no axis. The caller reports an undeclared entity separately.
    """
    try:
        return Entity(definition=resolve_effective_definition(entity_defs, entity_name))
    except (KeyError, RejectionError):
        return None


def _validate_buffered_write(
    instructions: list[Any],
    entity_defs: list[dict[str, Any]],
    predicate_schema: dict[str, Any],
    label: str,
    errors: list[str],
    registry: Registry | None = None,
    *,
    grouped: bool = False,
) -> None:
    """Validate a buffered scenario write — the m-unit-work general keyed buffer.

    The schema pins the STRUCTURAL shape (an ordered buffer of one-or-more KEYED
    instructions; predicate-selected entries are excluded). This adds the three
    model-aware checks JSON Schema cannot express and the wire harness would otherwise
    skip (it executes the flushed golden SQL, never the buffered instructions):

    * **member honesty** — each keyed row's keys MUST name declared attributes / value
      objects of its entity, so a buffered write cannot silently name a non-member
      (:func:`~reference_harness.keyed_write_validate.undeclared_row_members`). Asked
      FIRST, and the entry stops there when it fails: a row naming nothing real has no
      payload for an instruction rule to be about, which is the same precedence every
      other lane applies.
    * **the temporal singleton** — an entry on a temporal entity carries exactly ONE
      row (`m-unit-work` "A temporal keyed instruction carries exactly one row"),
      since each row closes its own milestone, consumes its own observation, and
      chains its own successors. The row count a keyed entry may carry depends on
      whether its target is temporal, which only the model knows, so the schema
      states the general one-or-more bound and the singleton is decided by
      :func:`~reference_harness.keyed_write_validate.validate_keyed_write` — the
      SAME function the `rejected` lane's keyed `when.write` reaches, so a buffer
      entry and a rejected instruction cannot be judged differently.
    * **framework provenance** — an entry assigning a DB-computed write marker states a
      statement the framework issues rather than a write a caller authors
      (:func:`~reference_harness.keyed_write_validate.states_framework_marker`), so it
      is a choreography unit of its own: the buffer's only entry, in an ungrouped step
      (`m-case-format` "Buffered keyed write instructions"). No public verb accepts such
      a value, so a mixed buffer would state half its DML through the write verbs and
      half around them, and a grouped one would ask that group's held unit of work to
      buffer an instruction it has no verb for.

    Same-object coalescing is NOT a structural property of the buffer: a general buffer
    legitimately spans different entities and different primary-key identities (a mixed
    multi-object flush, an abort pair over distinct objects). Coalescing correctness is
    proven where it always was — the step's golden SQL executed verbatim plus
    ``tableState`` / ``expectRows`` — so no cross-entry same-object equality is imposed
    here. A predicate entry is not part of the buffered shape (the schema forbids it);
    should a schema-invalid case still carry one, the predicate-write validator reports
    it rather than the keyed member check.
    """
    framework: list[int] = []
    for position, instruction in enumerate(instructions):
        entry_label = f"{label} buffered write[{position}]"
        if not isinstance(instruction, dict):
            continue  # the case schema owns non-object entries
        if "target" in instruction:
            _validate_predicate_write(
                instruction, entity_defs, predicate_schema, entry_label, errors, registry
            )
            continue
        entity_name = instruction.get("entity")
        if not isinstance(entity_name, str):
            continue  # the case schema owns the missing/malformed entity error
        entity = _effective_entity(entity_defs, entity_name)
        if entity is None:
            errors.append(f"{entry_label}: keyed write entity {entity_name!r} is not declared")
            continue
        unknown = undeclared_row_members(entity, instruction)
        if unknown:
            errors.append(
                f"{entry_label}: keyed write row names {unknown} which are not "
                f"attributes or value objects of {entity_name}"
            )
            continue
        try:
            validate_keyed_write(entity, instruction)
        except RejectionError as exc:
            errors.append(f"{entry_label}: {exc.detail}")
            continue
        if states_framework_marker(entity, instruction):
            framework.append(position)
    if not framework:
        return
    if grouped:
        errors.append(
            f"{label}: buffered write{framework} carries a DB-computed write marker inside a "
            f"`uow` group. Such an entry states the framework's own bookkeeping and is a "
            f"choreography unit of its own, which a group's held unit of work cannot buffer"
        )
    elif len(instructions) != 1:
        errors.append(
            f"{label}: buffered write{framework} carries a DB-computed write marker among "
            f"{len(instructions)} entries. Such an entry states the framework's own bookkeeping "
            f"and is a choreography unit of its own, so it is the buffer's only entry"
        )


# --- compile-eligibility backstop (m-case-format / m-conformance-adapter) -----
#
# A case is compile-eligible by default; it is declared RUN-ONLY (a top-level
# `compileEligibility` block) only when its emissions cannot be derived without
# executing SQL. Eligibility is an AUTHORED, reviewed intent declaration, but the
# harness mechanically backstops the DETECTABLE single-connection minority: any case
# that intends database concurrency or locking behavior — a `conflict` /
# `concurrencySuccess` / `boundary` shape, a `when.concurrency` choreography, or a
# `given.apply` / `given.fault` — is run-only regardless of whether its emissions
# happen to be statically derivable, so it MUST carry the declaration. (The
# query-result-dependence criterion is a human judgment the harness cannot detect;
# each language's refusing compile port enforces it structurally at runtime.)

_SINGLE_CONNECTION_SHAPES = frozenset({"conflict", "concurrencySuccess", "boundary"})


def _single_connection_markers(case: dict[str, Any]) -> list[str]:
    """Return the detectable single-connection markers a case carries (empty == none)."""
    markers: list[str] = []
    given = case.get("given")
    if isinstance(given, dict):
        if "apply" in given:
            markers.append("given.apply")
        if "fault" in given:
            markers.append("given.fault")
    when = case.get("when")
    if isinstance(when, dict) and "concurrency" in when:
        markers.append("when.concurrency")
    shape = case.get("shape")
    if shape in _SINGLE_CONNECTION_SHAPES:
        markers.append(f"shape:{shape}")
    return markers


def _check_compile_eligibility(case: Any, label: str, errors: list[str]) -> None:
    """Backstop the DETECTABLE compile-eligibility declarations.

    A case carrying a detectable single-connection marker MUST be declared compile
    run-only with reason ``single-connection``; leaving it compile-eligible (or
    mis-reasoning it) is a loud failure.
    """
    if not isinstance(case, dict):
        return
    markers = _single_connection_markers(case)
    if not markers:
        return
    declaration = case.get("compileEligibility")
    if not (isinstance(declaration, dict) and declaration.get("mode") == "run-only"):
        errors.append(
            f"{label}: carries single-connection compile marker(s) {markers} but is not "
            f"declared compile run-only (add `compileEligibility: {{mode: run-only, "
            f"reason: single-connection}}`)"
        )
        return
    if declaration.get("reason") != "single-connection":
        errors.append(
            f"{label}: single-connection marker(s) {markers} require "
            f"`compileEligibility.reason: single-connection`, not "
            f"{declaration.get('reason')!r}"
        )


def _validate_scenario_reference_sql(
    step: dict[str, Any], case_schema: dict[str, Any], label: str, errors: list[str]
) -> None:
    if "referenceSql" not in step:
        return
    reference_schema = case_schema["$defs"]["referenceSql"]
    _validate(step["referenceSql"], reference_schema, f"{label} referenceSql", errors)
    _scenario_reference_sql_dialect_keys(step, label, errors)


def _edited_target(steps: list[Any], index: int) -> str | None:
    """The Object Query target the `mutate` step at *index* edits, or ``None``.

    A `mutate` names an earlier step through ``on``: the find whose result it
    edits, or an earlier `mutate` whose copy it derives from, which the walk
    follows back to the find that materialized the chain. ``None`` means the step
    resolves to no query at all — an out-of-range or missing ``on``, or one naming
    a write step — which the runtime ``on`` rules own
    (:func:`~reference_harness.case_runner._assert_action_on`) and this check does
    not restate.
    """
    seen: set[int] = set()
    current = index
    while current not in seen:
        seen.add(current)
        step = steps[current] if 0 <= current < len(steps) else None
        on = step.get("on") if isinstance(step, dict) else None
        if not isinstance(on, int) or not 0 <= on < len(steps):
            return None
        source = steps[on]
        if not isinstance(source, dict):
            return None
        query = source.get("objectQuery")
        if isinstance(query, dict):
            target = query.get("target")
            return target if isinstance(target, str) else None
        if source.get("action") != "mutate":
            return None
        current = on
    return None


def _validate_scenario_edit(
    steps: list[Any],
    index: int,
    entity_defs: list[dict[str, Any]],
    family: Family | None,
    label: str,
    errors: list[str],
) -> None:
    """Refuse a `mutate` step whose `set` the model does not admit.

    `m-case-format` makes an assignment no member of the edited Entity admits a
    **case-authoring failure** rather than a graded observation: the closed
    `expectError` vocabulary has no member for it, so a case cannot declare the
    refusal and an executor reaching one has nothing portable to report. Refusing
    it statically is the same standard the bare write row's member honesty is held
    to, asked before any executor sees the case rather than by each of them.

    The Entity is the one the edited node IS, which an abstract-target read leaves
    open: such a read materializes complete concrete instances, so a subtype's own
    member is assignable on a node the query answered. The set is therefore judged
    against the target's EFFECTIVE CONCRETE SET and accepted where any member of it
    admits the assignment — the widest position the query could have answered, so
    the refusal reports only what no concrete could accept. A `narrowTo` clause can
    only shrink that set, so reading the bare target stays conservative.

    A refusal spanning a family is reported from a concrete that DECLARES the
    member where one does: every other concrete answers that the name is nothing of
    theirs, which is true and says less than the declared position's own verdict on
    the value.
    """
    step = steps[index]
    assignments = step.get("set") if isinstance(step, dict) else None
    if not isinstance(assignments, dict) or not assignments:
        return
    target = _edited_target(steps, index)
    if target is None:
        return
    positions = family.effective_concrete_set(target) if family is not None else [target]
    entities: list[Entity] = []
    for position in positions:
        entity = _effective_entity(entity_defs, position)
        if entity is None:
            return  # an undeclared target is the query validator's to report
        entities.append(entity)
    for name, value in assignments.items():
        judged = [(entity, assignment_violation(entity, name, value)) for entity in entities]
        if any(violation is None for _, violation in judged):
            continue
        declaring = [
            violation
            for entity, violation in judged
            if not undeclared_members(entity, {name: value}) and violation is not None
        ]
        reported = declaring or [violation for _, violation in judged if violation is not None]
        errors.append(f"{label}: `mutate` set {reported[0]}")


def validate_tree(compatibility_root: Path) -> list[str]:
    """Validate every schema and every fixture; return a list of error strings."""
    compatibility_root = compatibility_root.resolve()
    schema_map = load_schemas(compatibility_root)
    registry = build_registry(schema_map)
    errors: list[str] = []

    # 1. The schemas themselves are valid JSON Schema documents.
    for name, schema in schema_map.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - surface any meta-schema problem
            errors.append(f"meta-schema: {name} is not a valid JSON Schema: {exc}")

    metamodel_schema = schema_map["metamodel.schema.json"]
    predicate_schema = schema_map["predicate.schema.json"]
    object_query_schema = schema_map["object-query.schema.json"]
    case_schema = schema_map["compatibility-case.schema.json"]

    # 2. Every model descriptor validates against the metamodel schema, the
    #    foundational Index-identity rule, and the unconditional semantic
    #    validators for Inheritance and Storage Layout. Inheritance validates
    #    family topology when present; Storage Layout also validates standalone
    #    Table ownership and Column claims. A family resolver per model backs the
    #    family-aware query self-consistency cross-check below.
    models_dir = compatibility_root / "models"
    families: dict[str, Family] = {}
    model_entities: dict[str, list[dict[str, Any]]] = {}
    for model_path in sorted(models_dir.glob("**/*.y*ml")):
        descriptor = _load_yaml(model_path)
        _validate(descriptor, metamodel_schema, f"model {model_path.name}", errors)
        entity_defs = _descriptor_entity_defs(derive_temporal_structure(descriptor))
        families[model_path.name] = Family(entity_defs)
        model_entities[model_path.name] = entity_defs
        try:
            validate_index_identities(entity_defs)
            validate_family_defs(entity_defs)
            validate_storage_layout(entity_defs)
        except RejectionError as exc:
            errors.append(f"model {model_path.name}: {exc.rule}: {exc.detail}")

    # 3. Every case + the Object Queries it carries validate against their schemas.
    cases_dir = compatibility_root / "cases"
    for case_path in sorted(cases_dir.glob("**/*.y*ml")):
        case = _load_yaml(case_path)
        model_rel = case.get("model") if isinstance(case, dict) else None
        model_name = Path(model_rel).name if isinstance(model_rel, str) else None
        family = families.get(model_name) if model_name is not None else None
        # The execution oracle's referential and arithmetic checks read members the
        # case schema has already typed, so they run only once the case IS
        # schema-valid; on a schema-invalid case the structural diagnostics are the
        # answer and a semantic walk over unchecked shapes would raise instead.
        case_problem = validation_error(case, case_schema, registry)
        if case_problem is not None:
            errors.append(f"case {case_path.name}: {case_problem}")
        _check_compile_eligibility(case, f"case {case_path.name}", errors)
        if case_problem is None and isinstance(case, dict):
            errors.extend(
                f"case {case_path.name}: {problem}" for problem in validate_execution(case)
            )
        # The action under test lives under `when`; a read or rejected case's
        # Object Query and each scenario/coherence step's own are canonical
        # m-object-query documents that must also validate against that schema.
        when = case.get("when") if isinstance(case, dict) else None
        when = when if isinstance(when, dict) else {}
        if "objectQuery" in when:
            _check_object_query(
                when["objectQuery"],
                object_query_schema,
                family,
                f"case {case_path.name} objectQuery",
                errors,
                registry,
                model_aware=case.get("shape") == "read",
                encodings=when.get("equivalentEncodings"),
                encodings_label=f"case {case_path.name} equivalentEncodings",
            )
        # A scenario case carries its Object Query per step (under
        # `when.scenario[].objectQuery`); each one validates the same way.
        if isinstance(when.get("scenario"), list):
            for index, step in enumerate(when["scenario"]):
                if isinstance(step, dict) and "objectQuery" in step:
                    _check_object_query(
                        step["objectQuery"],
                        object_query_schema,
                        family,
                        f"case {case_path.name} scenario[{index}].objectQuery",
                        errors,
                        registry,
                        encodings=step.get("equivalentEncodings"),
                        encodings_label=(
                            f"case {case_path.name} scenario[{index}].equivalentEncodings"
                        ),
                    )
                    _validate_scenario_reference_sql(
                        step,
                        case_schema,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                    )
                if isinstance(step, dict) and isinstance(step.get("write"), dict):
                    entity = _validate_predicate_write(
                        step["write"],
                        model_entities.get(model_name or "", []),
                        predicate_schema,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                        registry,
                    )
                    if entity is not None:
                        try:
                            validate_predicate_write_materialization(
                                entity, when["scenario"][:index], step["write"]
                            )
                        except PredicateWriteValidationError as exc:
                            errors.append(f"case {case_path.name} scenario[{index}]: {exc}")
                if isinstance(step, dict) and step.get("action") == "mutate":
                    _validate_scenario_edit(
                        when["scenario"],
                        index,
                        model_entities.get(model_name or "", []),
                        family,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                    )
                if isinstance(step, dict) and isinstance(step.get("write"), list):
                    _validate_buffered_write(
                        step["write"],
                        model_entities.get(model_name or "", []),
                        predicate_schema,
                        f"case {case_path.name} scenario[{index}]",
                        errors,
                        registry,
                        grouped=isinstance(step.get("uow"), str),
                    )
        # A coherence case likewise carries read-step queries under
        # `when.coherence[].objectQuery`.
        if isinstance(when.get("coherence"), list):
            for index, step in enumerate(when["coherence"]):
                if isinstance(step, dict) and "objectQuery" in step:
                    _check_object_query(
                        step["objectQuery"],
                        object_query_schema,
                        family,
                        f"case {case_path.name} coherence[{index}].objectQuery",
                        errors,
                        registry,
                    )
        # The referenced model must exist.
        if isinstance(case, dict) and isinstance(case.get("model"), str):
            referenced = compatibility_root / case["model"]
            if not referenced.is_file():
                errors.append(f"case {case_path.name}: model {case['model']} does not exist")

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.schema_validate <core/compatibility>",
            file=sys.stderr,
        )
        return 2
    compatibility_root = Path(argv[0])
    if not compatibility_root.is_dir():
        print(f"not a directory: {compatibility_root}", file=sys.stderr)
        return 2

    errors = validate_tree(compatibility_root)
    if errors:
        print(f"schema validation FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("schema validation OK: all schemas and fixtures conform")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
