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
from parallax.core.metamodel import Metamodel as AcceptedMetamodel
from parallax.core.model_formation import MetamodelValidationError
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.predicate import CanonicalDocumentError, ModelRejectedError
from parallax.core.unit_work import (
    KeyedWrite,
    PredicateWrite,
    WritePlanningError,
    WriteRejectedError,
    instructions,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite
from parallax.core.unit_work.write_settlement import reject_readless_document_many
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
    (`handle.preflight`), which owns target resolution, so the two paths cannot
    drift. A `model` input first
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

    A `write` input is one of three, dispatched on the members the input itself
    carries (`m-case-format` Rejected cases) — never on the case's tags or
    filename. A `target` names a predicate-selected instruction; `rows` names a
    keyed instruction, which brings its own `entity` handle
    (:func:`_rejected_keyed_write`); anything else is the bare neutral write row
    (①), which names no handle at all and is therefore resolved against the
    model's default entity (`_rejected_target`'s own convention, reused here —
    the family root when the model declares one, else the model's single
    entity), wrapped as the canonical keyed instruction, and routed through
    the case-format preparation seam. That seam normalizes carriers and delegates
    recursive Wire decoding, validation, and retained-value freezing to
    :func:`~parallax.core.unit_work.instructions.prepare_wire_write`, so the
    rejected lane cannot drift from ordinary Wire write ingress.

    Membership can decide the form only because `target` and `rows` are RESERVED
    from a bare row at this position (`compatibility-case.schema.json`
    `$defs/bareWriteRow`): neither is a domain member name here, so no row can be
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
    if not isinstance(raw_write, Mapping):
        raise EngineError(
            f"{case.path.name}: a rejected `when.write` is a predicate-selected instruction, a "
            f"keyed instruction, or a bare neutral write row — all objects, and the members "
            f"decide which. {type(raw_write).__name__} is the conflict lane's multi-key form, "
            f"which asserts an aggregate affected-row count no rejected case emits SQL to "
            f"produce (m-case-format Rejected cases)"
        )
    row = cast("Mapping[str, object]", raw_write)
    if "target" in row:
        return _rejected_predicate_write(case, row, model)
    if "rows" in row:
        return _rejected_keyed_write(case, row, model)
    return _rejected_bare_row(case, row, model)


def _rejected_predicate_write(
    case: case_format.Case, row: Mapping[str, object], model: AcceptedMetamodel
) -> str:
    try:
        instruction = instructions.deserialize(case_document.canonical_predicate_doc(row))
    except WritePlanningError as exc:  # pragma: no cover - schema validation owns malformed writes
        raise EngineError(f"{case.path.name}: {exc}") from exc
    if not isinstance(instruction, PredicateWrite):  # pragma: no cover - target implies predicate
        raise EngineError(f"{case.path.name}: rejected predicate write decoded as keyed")
    try:
        prepared = _case_ingress.prepare_case_write(instruction, model)
        assert isinstance(prepared, PreparedPredicateWrite)
        target = case_entity(model, prepared.selection.target.identity.canonical)
        reject_readless_document_many(target, prepared)
    except (instructions.InstructionRejectedError, WriteRejectedError) as exc:
        return exc.rule
    raise EngineError(  # pragma: no cover - rejected cases must classify
        f"{case.path.name}: the model-aware validator accepted a predicate write the "
        "case expects rejected pre-SQL"
    )


def _rejected_bare_row(
    case: case_format.Case, row: Mapping[str, object], model: AcceptedMetamodel
) -> str:
    target = case_entity(model, _rejected_target(case, model))
    try:
        durable_row = {name: value for name, value in row.items() if name != "observedVersion"}
        instruction = KeyedWrite("insert", target.identity.canonical, (durable_row,))
        _case_ingress.prepare_case_write(instruction, model)
    except (instructions.InstructionRejectedError, WriteRejectedError) as exc:
        return exc.rule
    except instructions.WriteInstructionError as exc:
        raise EngineError(f"{case.path.name}: {exc}") from exc
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a write the case expects "
        "rejected pre-SQL"
    )


def _rejected_keyed_write(
    case: case_format.Case, authored: Mapping[str, object], model: AcceptedMetamodel
) -> str:
    """Grade a rejected `when.write` that is a KEYED INSTRUCTION, returning the rule.

    A keyed instruction names its own `entity`, so unlike the bare neutral write
    row beside it this input needs no default-target convention: the handle it is
    validated against is the one it authored. The canonical document is rebuilt
    from the instruction members alone, exactly as the writeSequence/scenario
    producer rebuilds it — the case format's `at` is harness Clock context and
    never an instruction field (`m-unit-work`), so it is not carried across.

    The refusal is the shared build-time
    case-format preparation seam's strict Wire producer — the
    Wire producer parallel to the typed producer every keyed developer verb runs
    before it buffers anything. It asks the concrete-subtype payload-shape rules
    (`m-inheritance` "Concrete-subtype writes") first, and they classify a
    framework-owned metadata key and a sibling-branch member more specifically
    than the generic member-name-honesty gate ever could, so a keyed update of
    `CardPayment` carrying `CashPayment`'s own attribute is
    `subtype-write-sibling-attribute` rather than an undeclared-member authoring
    failure. The keyed rejected lane, the bare-row lane, and the developer
    transaction reach that one classification through the same preparation.
    """
    doc: dict[str, object] = {
        key: authored[key]
        for key in ("mutation", "entity", "rows", "validFrom", "until")
        if key in authored
    }
    try:
        instruction = instructions.deserialize(doc)
    except (
        instructions.WriteInstructionError
    ) as exc:  # pragma: no cover - schema validation owns malformed writes
        raise EngineError(f"{case.path.name}: {exc}") from exc
    try:
        _case_ingress.prepare_case_write(instruction, model)
    except (instructions.InstructionRejectedError, WriteRejectedError) as exc:
        return exc.rule
    raise EngineError(
        f"{case.path.name}: the model-aware validator accepted a keyed write instruction the "
        "case expects rejected pre-SQL"
    )
