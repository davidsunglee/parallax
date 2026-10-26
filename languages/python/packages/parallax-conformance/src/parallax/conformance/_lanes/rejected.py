from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

from parallax.conformance import _case_ingress, case_format
from parallax.conformance._mechanism import case_document
from parallax.conformance._mechanism.envelope import EngineError
from parallax.conformance._mechanism.model_facts import (
    case_entity,
    default_family_root,
    first_declared_entity,
    gate_read,
    load_case_metamodel,
)
from parallax.core import inheritance
from parallax.core._execution._unit_work import instructions
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.predicate import CanonicalDocumentError, ModelRejectedError
from parallax.core.unit_work import (
    KeyedWriteInstruction,
    WriteRejectedError,
)
from parallax.descriptor import (
    DescriptorError,
    domain_model_from_document,
    validate_inheritance_families,
)

__all__ = ["run_rejected_case"]


def _rejected_target(case: case_format.Case, model: AcceptedMetamodel) -> str:
    """The queried/written root a `rejected` case's `when` omits.

    A `rejected` case's `when.write` input carries no explicit handle: the
    model-aware default `m-predicate` "the four-step validation rule" fixes is
    the inheritance family root when the model declares one, else the model's own
    first entity. It is the entity the prepared-write producer checks the payload against. A
    `when.objectQuery` case names its own queried position and reaches none of
    this.

    Reported by CANONICAL spelling: the root arrives here as accepted Metadata,
    so its Identity is already resolved, and spelling it bare would put a
    selection the case never authored back through the ambiguity rule that
    adjudicates an authored one — where a local name two namespaces share
    resolves to nothing and a local name an ownerless sibling also carries
    resolves to that sibling.
    """
    root = default_family_root(model)
    if root is not None:
        return root.identity.canonical
    return first_declared_entity(case)


# The `rejected` shape's schema `oneOf`: exactly one of these keys, never zero
# or more than one (m-case-format).
_REJECTED_WHEN_KINDS: Final[tuple[str, ...]] = ("objectQuery", "model", "write")


def _rejected_when_kind(case: case_format.Case, when: Mapping[str, object]) -> str:
    """The `rejected` case's single recognized `when` input, enforcing the
    schema's `oneOf` (m-case-format): a caller that reaches the engine without
    schema validation (or a hand-built two-input synthetic case) must not
    silently dispatch on the first recognized key — zero or more than one
    recognized input is a loud, named refusal, mirroring the harness's own
    mirror guard for this rule.
    """
    present = [kind for kind in _REJECTED_WHEN_KINDS if kind in when]
    if len(present) != 1:
        raise EngineError(
            f"{case.path.name}: a `rejected` case must carry EXACTLY ONE of "
            f"`when.objectQuery` / `when.model` / `when.write` (m-case-format schema "
            f"`oneOf`); found {present!r}"
        )
    return present[0]


def run_rejected_case(case: case_format.Case) -> str:
    """Grade a `rejected` case's pre-SQL refusal, returning the classified rule.

    A `rejected` case carries EXACTLY ONE of `when.objectQuery` / `when.model` /
    `when.write` (m-case-format schema `oneOf`) — enforced by
    :func:`_rejected_when_kind` before dispatch, since the schema `oneOf` cannot
    protect a caller that reaches this engine without schema validation. An
    `objectQuery` input is deserialized through the same `m-object-query` serde
    every read uses, then checked by production's own read gate
    (`execution._read_query.resolve_read_query`), which owns target resolution, so
    the two paths cannot drift. A `model` input first
    passes the descriptor frontend's own pre-formation family validator
    (:func:`~parallax.descriptor.validate_inheritance_families`) for descriptor
    spellings the accepted algebra cannot represent, then goes through the same
    public :func:`~parallax.descriptor.domain_model_from_document` door every
    reusable corpus model does. **That order is load-bearing, not incidental**:
    the document door gates on the canonical schema FIRST, and four inline
    `rejected` models violate that schema on purpose, so forming first would
    report each as a `DescriptorSchemaError` instead of the family rule the case
    authored. The family validator parses shape only and has no schema phase,
    which is exactly why it can answer for a document expected never to form.

    A `write` input is one of four, dispatched in order on the members the input
    itself carries (`m-case-format` Rejected cases) — never on the case's tags or
    filename — and adapted once to the instruction it denotes
    (:func:`_rejected_instruction`). Every form is then graded through the one
    case-format preparation seam, which normalizes carriers and delegates
    recursive Wire decoding, validation, and retained-value freezing to
    :func:`~parallax.core._execution._unit_work.instructions.prepare_wire_write`, so the
    rejected lane cannot drift from ordinary Wire write ingress. A classified
    refusal is the rule; an unclassified one, or acceptance, fails the case.

    Membership can decide the form only because `target`, `rows`, and `row` are
    RESERVED from a bare row at this position (`compatibility-case.schema.json`
    `$defs/bareWriteRow`): none is a domain member name here, so no row can be
    re-read as an instruction and no instruction as a row. It can decide it only
    for an OBJECT at all, so the multi-key ARRAY the shared `when.write`
    vocabulary carries for the conflict lane is refused here by shape, before any
    member is asked for.

    Raises :class:`EngineError` if the input is unexpectedly accepted (no rule
    violation detected) — the caller compares the returned rule against the
    case's `then.rejectedRule`.
    """
    when = case_document.when(case)
    kind = _rejected_when_kind(case, when)
    model = load_case_metamodel(case)
    if kind == "objectQuery":
        return _rejected_object_query(case, when["objectQuery"], model)
    if kind == "model":
        return _rejected_model(case, cast("Mapping[str, object]", when["model"]))
    return _rejected_write(case, when["write"], model)


def _rejected_object_query(
    case: case_format.Case, authored: object, model: AcceptedMetamodel
) -> str:
    try:
        query = deserialize_query(authored)
    except CanonicalDocumentError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    query = _case_ingress.normalize_case_query(query, model)
    try:
        gate_read(query, model)
    except ModelRejectedError as exc:
        return exc.rule
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted an Object Query the case "
        "expects rejected pre-SQL"
    )


def _rejected_model(case: case_format.Case, inline_model: Mapping[str, object]) -> str:
    try:
        validate_inheritance_families(inline_model)
    except inheritance.InheritanceError as exc:
        return exc.rule
    except DescriptorError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    try:
        domain_model_from_document(inline_model)
    except DescriptorError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    except MetamodelValidationError as exc:
        codes = tuple(issue.code for issue in exc.issues)
        if len(codes) != 1:
            raise EngineError(
                f"{case.path.name}: inline model produced {len(codes)} formation issues "
                f"{codes!r}; a rejected case must isolate exactly one rule"
            ) from exc
        return codes[0]
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted an inline model the case "
        "expects rejected pre-SQL"
    )


def _rejected_write(case: case_format.Case, raw_write: object, model: AcceptedMetamodel) -> str:
    """Adapt the one `when.write` input to its instruction, then grade it
    through the single case-format preparation every form shares."""
    if not isinstance(raw_write, Mapping):
        raise EngineError(
            f"{case.path.name}: a rejected `when.write` is a predicate-selected, keyed, or "
            f"target instruction, or a bare neutral write row — all objects, and the members "
            f"decide which. {type(raw_write).__name__} is the conflict lane's multi-key form, "
            f"which asserts an aggregate affected-row count no rejected case emits SQL to "
            f"produce (m-case-format Rejected cases)"
        )
    instruction = _rejected_instruction(case, cast("Mapping[str, object]", raw_write), model)
    try:
        _case_ingress.prepare_case_write(instruction, model)
    except (instructions.InstructionRejectedError, WriteRejectedError) as exc:
        return exc.rule
    except instructions.WriteInstructionError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a write the case expects "
        "rejected pre-SQL"
    )


# The members a keyed `when.write` carries into its canonical instruction; any
# other member is case context, such as the Clock's `at`, and never an
# instruction field (`m-unit-work`).
_KEYED_INSTRUCTION_MEMBERS: Final[tuple[str, ...]] = (
    "mutation",
    "entity",
    "rows",
    "validFrom",
    "until",
)


def _rejected_instruction(
    case: case_format.Case, authored: Mapping[str, object], model: AcceptedMetamodel
) -> instructions.WriteInstruction:
    """The instruction a rejected `when.write` puts under test.

    A `target` names a predicate-selected instruction, deserialized whole, so a
    predicate replacement's `row` stays its payload. Otherwise `rows` names a
    keyed instruction, which brings its own `entity` handle: its document is
    rebuilt from the instruction members alone, exactly as the
    writeSequence/scenario producer rebuilds one, once the input is known to carry
    no other instruction's carrier — filtering first would discard that carrier
    and grade a malformed input as though it were well formed. Otherwise `row`
    names a target instruction, deserialized whole. Anything else is the bare
    neutral write row (①), which names no handle: it is resolved against the
    model's default entity (:func:`_rejected_target`) and wrapped as a keyed
    insert, its flush-time `observedVersion` context set aside.
    """
    if "target" in authored:
        return _deserialized(case, authored)
    if "rows" in authored:
        if "row" in authored:
            raise EngineError(
                f"{case.path.name}: a keyed `when.write` carries `rows` and also `row`, which "
                "names another instruction form (m-case-format Rejected cases)"
            )
        return _deserialized(
            case, {key: authored[key] for key in _KEYED_INSTRUCTION_MEMBERS if key in authored}
        )
    if "row" in authored:
        return _deserialized(case, authored)
    target = case_entity(model, _rejected_target(case, model))
    durable_row = {name: value for name, value in authored.items() if name != "observedVersion"}
    try:
        return KeyedWriteInstruction("insert", target.identity.canonical, (durable_row,))
    except instructions.WriteInstructionError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc


def _deserialized(
    case: case_format.Case, document: Mapping[str, object]
) -> instructions.WriteInstruction:
    try:
        return instructions.deserialize(document)
    except instructions.WriteInstructionError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
