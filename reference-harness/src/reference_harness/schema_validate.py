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
from .inheritance import (
    Family,
    resolve_clamped_narrow,
    resolve_effective_definition,
    validate_family_defs,
)
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


_SAME_ENTITY_DERIVATIONS: frozenset[str] = frozenset({"mutate", "detachCopy", "mergeBack"})
"""The action verbs whose result stands exactly where the step they name stands.

An edited copy, a detached deep copy and a merged-back object are all the object
their source step held, so a chain of them stands at the position the step the
chain started from answered at.
"""

_RELATIONSHIP_NAVIGATIONS: frozenset[str] = frozenset({"load", "access"})
"""The action verbs whose result stands where their ``path`` leads.

A `load` / `access` carrying a `path` holds the objects that path's LAST hop
reaches — an `access` on `items` holds OrderItems, never the Order it navigated
from — so the position it stands at is the relationship's target rather than its
source's. The path-less `access` form navigates nothing (it resolves a
query-backed list, `m-op-list`), so its members stand where its source does.
"""


type _Position = tuple[str, ...]
"""Where a scenario step's result stands: every concrete Entity a node there could be.

A position is known by its concretes and by nothing else — never by a declared
position name — because both model questions the walk asks are questions about the
node itself, and a node is one concrete. Which relationship a `path` hop names is
asked of each concrete (:func:`_navigated_position`, through the applicable
declaration on that concrete's ancestry), and which assignments it admits is asked
of each concrete too (:func:`_validate_scenario_edit`). So a member reaches a
descendant by inheritance exactly as one declared on it does.

The empty tuple is a position no concrete instance stands at; ``None``, which is
never a ``_Position``, is a position this check cannot decide.
"""


def _entity_position(entity: str, family: Family | None) -> _Position:
    """*entity* as a position, over every concrete a node standing there could be."""
    if family is None:
        return (entity,)
    return tuple(family.effective_concrete_set(entity))


def _query_position(query: dict[str, Any], family: Family | None) -> _Position | None:
    """An Object Query's **result** position — ``target`` as narrowed by ``narrowTo``.

    `m-object-query` makes the Subtype Selection the position the query answers
    at, so a narrowed read contributes only the concretes it can still return. An
    abstract position contributes its whole effective concrete set, because such a
    read materializes complete concrete instances and the case does not say which
    one any node it hands over is.

    A selection that does not resolve INSIDE the queried position states no
    position, and falls back to the unnarrowed one: narrowing only ever removes
    candidates, so the whole queried set is the strictest reading available and
    cannot admit an assignment some coherent narrowing would refuse.
    """
    target = query.get("target")
    if not isinstance(target, str):
        return None
    queried = _entity_position(target, family)
    narrow_to = query.get("narrowTo")
    if family is None or not isinstance(narrow_to, list):
        return queried
    try:
        narrowed = resolve_clamped_narrow(family, list(queried), narrow_to)
    except RejectionError:
        return queried
    return tuple(family.canonical_concrete_order(narrowed))


def _navigated_position(source: _Position, path: str, family: Family | None) -> _Position | None:
    """Where a `load` / `access` of *path* from *source* lands, or ``None``.

    Each hop is resolved from EVERY concrete the source position holds, through the
    relationship APPLICABLE to that concrete — its own declaration or an ancestor's,
    since `m-inheritance` makes a relationship declared on an ancestor a member of
    every concrete descendant under the ancestor's identity. So an `access` on
    `owner` from a `Dog` reaches the `Person` that `Animal.owner` names, exactly as
    it does from an `Animal`, and the edit that follows is judged there rather than
    slipping through unjudged. Where the source concretes reach different targets,
    the hop lands on the union of what each reaches, deduplicated by first
    appearance, because a node there may be any one of them.

    A hop SOME concrete of the position does not have states no position at all:
    the navigation is one the step cannot make from every node it may hold, and
    guessing past it would judge an edit against an Entity that node never becomes.

    Every hop is taken BROAD, at the relationship target's own effective concrete
    set, even where the source read's Include Paths narrowed that hop's view. That
    can only over-state the candidates, and a wider candidate set is the stricter
    judgement — so it can refuse a narrowed case an executor would have run, and
    can never pass one an executor refuses.
    """
    if family is None:
        return None
    position = source
    for hop in path.split("."):
        if not position:
            return None
        reached: list[str] = []
        for concrete in position:
            target = family.applicable_relationship_target(concrete, hop)
            if target is None:
                return None
            reached.extend(
                landing
                for landing in family.effective_concrete_set(target)
                if landing not in reached
            )
        position = tuple(reached)
    return position


def _source_index(step: dict[str, Any], *, grouped: bool) -> int | None:
    """The earlier step this action's ``on`` names, or ``None`` for no single one.

    A `load` spanning sources at DIFFERENT lowered coordinates names them as an
    ARRAY (`m-deep-fetch`); those sources are one position pinned several ways, so
    the first of them stands for the position they all stand at. Every other verb
    acts on a single object, where an array names no one node to resolve.
    """
    on = step.get("on")
    if grouped and isinstance(on, list):
        on = on[0] if on else None
    return on if isinstance(on, int) and not isinstance(on, bool) else None


def _step_position(
    steps: list[Any], index: int, family: Family | None, visited: frozenset[int] = frozenset()
) -> _Position | None:
    """Where the result of the scenario step at *index* stands, or ``None``.

    A read step stands at its own query's result position (:func:`_query_position`).
    An action step stands wherever its ``on`` chain leads: the same position for a
    same-Entity derivation (:data:`_SAME_ENTITY_DERIVATIONS`), the navigated one
    for a relationship read (:data:`_RELATIONSHIP_NAVIGATIONS`).

    ``None`` means the position is undecidable here rather than absent. A write
    step or a boundary verb holds no queried node; an out-of-range or missing
    ``on`` is the runtime ``on`` rules'
    (:func:`~reference_harness.case_assertions.assert_step_on_sources`) to report
    rather than this check's to restate; and a step reachable from itself resolves
    nowhere, which the cycle guard answers rather than looping.
    """
    if index in visited or not 0 <= index < len(steps):
        return None
    step = steps[index]
    if not isinstance(step, dict):
        return None
    query = step.get("objectQuery")
    if isinstance(query, dict):
        return _query_position(query, family)
    action = step.get("action")
    navigates = action in _RELATIONSHIP_NAVIGATIONS
    if not navigates and action not in _SAME_ENTITY_DERIVATIONS:
        return None
    source_index = _source_index(step, grouped=navigates)
    if source_index is None:
        return None
    source = _step_position(steps, source_index, family, visited | {index})
    if source is None or not navigates:
        return source
    path = step.get("path")
    if path is None:
        return source
    return _navigated_position(source, path, family) if isinstance(path, str) else None


def _validate_scenario_edit(
    steps: list[Any],
    index: int,
    entity_defs: list[dict[str, Any]],
    family: Family | None,
    label: str,
    errors: list[str],
) -> None:
    """Refuse a `mutate` step whose `set` the node it edits may not admit.

    `m-case-format` makes an assignment no member of the edited Entity admits a
    **case-authoring failure** rather than a graded observation: the closed
    `expectError` vocabulary has no member for it, so a case cannot declare the
    refusal and an executor reaching one has nothing portable to report. Refusing
    it statically is the same standard the bare write row's member honesty is held
    to, asked before any executor sees the case rather than by each of them.

    The Entity is the one the edited node IS, which an executor resolves from the
    node's own materialized variant and this check cannot see. What it has instead
    is the position that node stands at (:func:`_step_position`) — the position the
    step's own ``on`` chain reaches, which is a relationship's target where the
    chain runs through a `load` / `access` and the find's own result otherwise. The
    set must be one EVERY concrete of that position admits, WHOLE. That is what
    makes the static verdict the same verdict a validating executor reaches at run
    time: a set every candidate admits is admitted by whichever candidate the read
    answered. Accepting a set some ONE concrete admits would not — an `Animal` read
    narrowed to `Dog` and assigning `Cat`'s `indoor`, or an unnarrowed one
    assigning `Dog`'s `barkVolume` beside `Cat`'s `indoor`, names a node no read
    can hand an executor, which would then refuse the case this check had passed.

    Each candidate is judged over its APPLICABLE members — the ones it declares and
    the ones it inherits alike (:func:`~reference_harness.inheritance.resolve_effective_definition`)
    — because that is the set a node of that Entity actually carries. A case reaches
    a narrower position by NARROWING its read, and narrow enough is a position every
    concrete of which admits the whole set: `Animal` narrowed to the abstract `Pet`
    may assign `licenseId`, which `Pet` declares and both `Cat` and `Dog` inherit,
    while `Cat`'s own `indoor` needs the narrowing that leaves `Cat` alone. So the
    refusal distinguishes the two things an author can be told
    (:func:`_edit_refusal`).
    """
    step = steps[index]
    assignments = step.get("set") if isinstance(step, dict) else None
    if not isinstance(assignments, dict) or not assignments:
        return
    position = _step_position(steps, index, family)
    if position is None:
        return
    entities: list[Entity] = []
    for concrete in position:
        entity = _effective_entity(entity_defs, concrete)
        if entity is None:
            return  # an undeclared position is the query validator's to report
        entities.append(entity)
    judged = [(entity, _first_violation(entity, assignments)) for entity in entities]
    if all(violation is None for _, violation in judged):
        return
    errors.append(f"{label}: `mutate` set {_edit_refusal(judged, assignments)}")


def _first_violation(entity: Entity, assignments: dict[str, Any]) -> str | None:
    """Why *entity* refuses the first assignment in *assignments* it cannot take.

    The whole set is one judgement: *entity* admits it only when it admits every
    entry, so the first refusal ends the walk and stands for the set.
    """
    for name, value in assignments.items():
        violation = assignment_violation(entity, name, value)
        if violation is not None:
            return violation
    return None


def _edit_refusal(judged: list[tuple[Entity, str | None]], assignments: dict[str, Any]) -> str:
    """The refusal to report for a `set` some concrete of the edited position rejects.

    Two different things can be wrong, an author acts on them differently, and so
    they are not one message.

    Where SOME candidate would have admitted the set, the POSITION is what is too
    wide: the set describes a node the step may or may not reach, and what makes
    the case legal is editing at a position every concrete of which admits the set
    — not necessarily ONE concrete, since an abstract subtype whose concretes all
    admit it is narrow enough. So the refusal names the alternatives, states the
    bar, and names `narrowTo` as the clause a read reaches a narrower position by.

    Where EVERY candidate refuses, the assignment is wrong wherever it lands. It is
    reported from the candidate that HAS the most of the named members — applicable
    members, the ones it inherits counted with the ones it declares
    (:func:`~reference_harness.write_validate.undeclared_members`) — because a
    concrete that has none of them only answers that the names are nothing of
    theirs, which is true and says less than the verdict of a candidate the member
    is real on.
    """
    refused = [(entity, violation) for entity, violation in judged if violation is not None]
    if len(judged) == 1:
        return refused[0][1]
    answered = ", ".join(entity.name for entity, _ in judged)
    if len(refused) < len(judged):
        return (
            f"{refused[0][1]} — the edited node is any of ({answered}), so the set must be one "
            f"every one of them admits; a read narrows to such a position with `narrowTo`"
        )
    closest = min(refused, key=lambda candidate: len(undeclared_members(candidate[0], assignments)))
    return f"{closest[1]} — no concrete the edited node may be ({answered}) admits the whole set"


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
