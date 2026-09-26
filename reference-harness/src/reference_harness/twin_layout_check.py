"""Validate the compatibility corpus's cross-layout twin proofs.

The corpus authors one production descriptor and one production case per Storage
Layout arm. This checker proves the authored inputs and logical expectations are
twins; the ordinary compatibility sweep proves each member against its own
physical SQL, binds, and table state.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from reference_harness.case_twins import (
    case_twin_arms,
    logical_case,
    mapping_document,
    module_ids,
    primary_module,
    twin_arms,
    yaml_paths,
)
from reference_harness.dep_graph_check import MODULE_SLUG

_ARM = r"columns|document"
_MODEL_RE = re.compile(rf"^(?P<proof>.+)-layout-twin-(?P<arm>{_ARM})\.ya?ml$")
_CASE_TWIN_RE = re.compile(rf"^(?P<prefix>.+)-layout-twin-(?P<arm>{_ARM})\.ya?ml$")
_MODULE_TAG_RE = re.compile(rf"^{MODULE_SLUG}$")
_ARMS = ("columns", "document")


def _entity_declarations(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    single = document.get("entity")
    if isinstance(single, Mapping):
        return [single]
    several = document.get("entities")
    if not isinstance(several, list):
        return []
    return [entry for entry in several if isinstance(entry, Mapping)]


def _is_layout_owner(entity: Mapping[str, Any]) -> bool:
    inheritance = entity.get("inheritance")
    return not isinstance(inheritance, Mapping) or inheritance.get("role") == "root"


def _logical_descriptor(document: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(document)
    single = normalized.get("entity")
    if isinstance(single, Mapping):
        entity = dict(single)
        entity.pop("layout", None)
        normalized["entity"] = entity
    several = normalized.get("entities")
    if isinstance(several, list):
        entities: list[Any] = []
        for entry in several:
            if isinstance(entry, Mapping):
                entity = dict(entry)
                entity.pop("layout", None)
                entities.append(entity)
            else:
                entities.append(entry)
        normalized["entities"] = entities
    return normalized


def _layout_errors(path: Path, arm: str, document: Mapping[str, Any]) -> list[str]:
    entities = _entity_declarations(document)
    layouts = [entity.get("layout") for entity in entities]
    present = [layout for layout in layouts if layout is not None]
    if arm == "columns":
        return (
            [f"{path.name}: Columns twin must spell Columns by omitting every layout block"]
            if present
            else []
        )
    errors: list[str] = []
    for entity in entities:
        layout = entity.get("layout")
        name = entity.get("name", "<unnamed>")
        if not _is_layout_owner(entity):
            if layout is not None:
                errors.append(f"{path.name}: descendant {name} must omit its inherited layout")
            continue
        document_arm = layout.get("document") if isinstance(layout, Mapping) else None
        column = document_arm.get("column") if isinstance(document_arm, Mapping) else None
        if not isinstance(column, str) or not column:
            errors.append(f"{path.name}: {name} mapping owner must declare layout.document.column")
    return errors


def _refuse_incomplete[K](pairs: dict[K, dict[str, Path]], kind: str, errors: list[str]) -> None:
    """A layout twin states one behavior in BOTH storage layouts or states nothing."""
    for key, members in pairs.items():
        missing = [arm for arm in _ARMS if arm not in members]
        if missing:
            errors.append(f"{kind} twin {key!r} is missing {', '.join(missing)} member(s)")


def _descriptor_pairs(compatibility_root: Path, errors: list[str]) -> dict[str, dict[str, Path]]:
    candidates: list[tuple[str, str, Path]] = []
    for path in yaml_paths(compatibility_root / "models"):
        match = _MODEL_RE.match(path.name)
        if match is not None:
            candidates.append((match.group("proof"), match.group("arm"), path))
    pairs = twin_arms(candidates, "descriptor", errors)
    _refuse_incomplete(pairs, "descriptor", errors)
    return pairs


def _case_pairs(
    paths: list[Path], modules: frozenset[str], errors: list[str]
) -> dict[tuple[str, str], dict[str, Path]]:
    pairs = case_twin_arms(paths, _CASE_TWIN_RE, modules, "case", errors)
    _refuse_incomplete(pairs, "case", errors)
    return pairs


def _normalize_model_reference(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    path = Path(value)
    match = _MODEL_RE.match(path.name)
    if match is None:
        return value
    return str(path.with_name(f"{match.group('proof')}-layout-twin-<arm>.yaml"))


def _is_module_tag(tag: str) -> bool:
    return _MODULE_TAG_RE.fullmatch(tag) is not None


def _logical_case(document: Mapping[str, Any]) -> Any:
    """A layout twin's case document reduced to its layout-INVARIANT behavior.

    The two arms name different descriptor files by construction, so the model
    reference is normalized to the shared proof rather than dropped: an arm
    referencing another proof's descriptor must still fail.
    """
    return logical_case(document, rewrite=_normalize_model_reference)


def twin_layout_errors(compatibility_root: Path) -> list[str]:
    """Return every cross-layout corpus inconsistency under *compatibility_root*."""
    errors: list[str] = []
    if not compatibility_root.is_dir():
        return [f"not a directory: {compatibility_root}"]

    descriptor_pairs = _descriptor_pairs(compatibility_root, errors)
    fixtures = compatibility_root / "fixtures"
    for proof, members in descriptor_pairs.items():
        if any(arm not in members for arm in _ARMS):
            continue
        _check_descriptor_twin(proof, members, errors)
        _check_fixture_twin(fixtures, proof, errors)

    cases = compatibility_root / "cases"
    modules = module_ids(compatibility_root, errors)
    case_pairs = _case_pairs(yaml_paths(cases), modules, errors)
    used_descriptors: set[str] = set()
    for key, members in case_pairs.items():
        if any(arm not in members for arm in _ARMS):
            continue
        used = _check_case_twin(key, members, modules, set(descriptor_pairs), errors)
        if used is not None:
            used_descriptors.add(used)

    for proof in sorted(set(descriptor_pairs) - used_descriptors):
        errors.append(f"descriptor twin {proof!r} is not used by a complete case twin")
    return errors


def _check_descriptor_twin(proof: str, members: dict[str, Path], errors: list[str]) -> None:
    documents: dict[str, dict[str, Any]] = {}
    for arm in _ARMS:
        path = members[arm]
        document = mapping_document(path, "model descriptor", errors)
        if document is None:
            continue
        documents[arm] = document
        errors.extend(_layout_errors(path, arm, document))
    if all(arm in documents for arm in _ARMS) and _logical_descriptor(
        documents["columns"]
    ) != _logical_descriptor(documents["document"]):
        errors.append(
            f"descriptor twin {proof!r} differs after root-owned layout blocks are removed"
        )


def _check_fixture_twin(fixtures: Path, proof: str, errors: list[str]) -> None:
    fixture_documents: dict[str, dict[str, Any]] = {}
    for arm in _ARMS:
        fixture_path = fixtures / f"{proof}-layout-twin-{arm}.yaml"
        if not fixture_path.is_file():
            errors.append(f"descriptor twin {proof!r} is missing fixture {fixture_path.name}")
            continue
        fixture = mapping_document(fixture_path, "fixture", errors)
        if fixture is not None:
            fixture_documents[arm] = fixture
    if (
        all(arm in fixture_documents for arm in _ARMS)
        and fixture_documents["columns"] != fixture_documents["document"]
    ):
        errors.append(f"fixture twin {proof!r} does not author equal logical rows")


def _check_case_twin(
    key: tuple[str, str],
    members: dict[str, Path],
    modules: frozenset[str],
    descriptor_proofs: set[str],
    errors: list[str],
) -> str | None:
    """Check one complete case twin; return the descriptor twin both arms reference."""
    documents: dict[str, dict[str, Any]] = {}
    model_proofs: dict[str, str] = {}
    for arm in _ARMS:
        path = members[arm]
        case = mapping_document(path, "compatibility case", errors)
        if case is None:
            continue
        documents[arm] = case
        _check_case_module_tag(path, case, key[0], modules, errors)
        model_proof = _case_model_proof(path, arm, case, descriptor_proofs, errors)
        if model_proof is not None:
            model_proofs[arm] = model_proof
    used: str | None = None
    if all(arm in model_proofs for arm in _ARMS):
        if model_proofs["columns"] != model_proofs["document"]:
            errors.append(f"case twin {key!r} references two different descriptor twins")
        else:
            used = model_proofs["columns"]
    if all(arm in documents for arm in _ARMS) and _logical_case(
        documents["columns"]
    ) != _logical_case(documents["document"]):
        errors.append(f"case twin {key!r} differs in layout-invariant authored behavior")
    return used


def _check_case_module_tag(
    path: Path,
    case: Mapping[str, Any],
    filename_module: str,
    modules: frozenset[str],
    errors: list[str],
) -> None:
    module_tag = primary_module(case, _is_module_tag)
    if module_tag is not None and module_tag not in modules:
        errors.append(
            f"{path.name}: first module tag {module_tag!r} is not in the canonical module catalog"
        )
    elif module_tag != filename_module:
        errors.append(
            f"{path.name}: filename module {filename_module!r} does not match first "
            f"module tag {module_tag!r}"
        )


def _case_model_proof(
    path: Path,
    arm: str,
    case: Mapping[str, Any],
    descriptor_proofs: set[str],
    errors: list[str],
) -> str | None:
    """The descriptor twin a case arm references, or ``None`` when it names no twin."""
    model = case.get("model")
    model_name = Path(model).name if isinstance(model, str) else ""
    model_match = _MODEL_RE.match(model_name)
    if model_match is None:
        errors.append(f"{path.name}: twin case must reference a twin model descriptor")
        return None
    model_arm = model_match.group("arm")
    model_proof = model_match.group("proof")
    if model_arm != arm:
        errors.append(f"{path.name}: {arm} case references the {model_arm} descriptor arm")
    if model_proof not in descriptor_proofs:
        errors.append(f"{path.name}: references unknown descriptor twin {model_proof!r}")
    return model_proof


def run(compatibility_root: Path) -> int:
    """Run the twin-layout gate and print a concise verdict."""
    errors = twin_layout_errors(compatibility_root)
    if errors:
        print(f"twin-layout gate FAILED ({len(errors)} problem(s)):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("twin-layout gate OK: every descriptor, fixture, and case twin is paired and equal")
    return 0


def main(argv: list[str]) -> int:
    """CLI entry point for ``python -m reference_harness.twin_layout_check``."""
    if len(argv) != 1:
        print(
            "usage: python -m reference_harness.twin_layout_check <compatibility-dir>",
            file=sys.stderr,
        )
        return 2
    return run(Path(argv[0]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
