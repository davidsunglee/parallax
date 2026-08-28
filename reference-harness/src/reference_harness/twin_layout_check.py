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
    logical_case,
    mapping_document,
    module_and_body,
    module_ids,
    primary_module,
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


def _pairs(
    paths: list[Path], pattern: re.Pattern[str], kind: str, errors: list[str]
) -> dict[tuple[str, ...], dict[str, Path]]:
    candidates: list[tuple[tuple[str, ...], str, Path]] = []
    for path in paths:
        match = pattern.match(path.name)
        if match is None:
            continue
        groups = match.groupdict()
        arm = groups.pop("arm")
        key = tuple(groups[name] for name in sorted(groups))
        candidates.append((key, arm, path))
    return _collect_pairs(candidates, kind, errors)


def _collect_pairs(
    candidates: list[tuple[tuple[str, ...], str, Path]], kind: str, errors: list[str]
) -> dict[tuple[str, ...], dict[str, Path]]:
    pairs: dict[tuple[str, ...], dict[str, Path]] = {}
    for key, arm, path in candidates:
        members = pairs.setdefault(key, {})
        previous = members.get(arm)
        if previous is not None:
            errors.append(
                f"{kind} twin {key!r} has two {arm} members: {previous.name}, {path.name}"
            )
        else:
            members[arm] = path
    for key, members in pairs.items():
        missing = [arm for arm in _ARMS if arm not in members]
        if missing:
            errors.append(f"{kind} twin {key!r} is missing {', '.join(missing)} member(s)")
    return pairs


def _descriptor_pairs(compatibility_root: Path, errors: list[str]) -> dict[str, dict[str, Path]]:
    models = compatibility_root / "models"
    raw = _pairs(yaml_paths(models), _MODEL_RE, "descriptor", errors)
    return {key[0]: members for key, members in raw.items()}


def _case_pairs(
    paths: list[Path], modules: frozenset[str], errors: list[str]
) -> dict[tuple[str, str], dict[str, Path]]:
    candidates: list[tuple[tuple[str, ...], str, Path]] = []
    for path in paths:
        twin = _CASE_TWIN_RE.match(path.name)
        if twin is None:
            continue
        parsed = module_and_body(twin.group("prefix"), modules)
        if parsed is None:
            errors.append(
                f"{path.name}: twin case name must begin with a catalog module and "
                "three-digit case sequence"
            )
            continue
        arm = twin.group("arm")
        candidates.append((parsed, arm, path))
    return {
        (key[0], key[1]): members
        for key, members in _collect_pairs(candidates, "case", errors).items()
    }


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
    descriptor_documents: dict[tuple[str, str], dict[str, Any]] = {}
    fixtures = compatibility_root / "fixtures"
    for proof, members in descriptor_pairs.items():
        if any(arm not in members for arm in _ARMS):
            continue
        for arm in _ARMS:
            path = members[arm]
            document = mapping_document(path, "model descriptor", errors)
            if document is None:
                continue
            descriptor_documents[(proof, arm)] = document
            errors.extend(_layout_errors(path, arm, document))
        columns = descriptor_documents.get((proof, "columns"))
        document = descriptor_documents.get((proof, "document"))
        if columns is not None and document is not None:
            if _logical_descriptor(columns) != _logical_descriptor(document):
                errors.append(
                    f"descriptor twin {proof!r} differs after root-owned layout blocks are removed"
                )

        fixture_documents: dict[str, dict[str, Any]] = {}
        for arm in _ARMS:
            fixture_path = fixtures / f"{proof}-layout-twin-{arm}.yaml"
            if not fixture_path.is_file():
                errors.append(f"descriptor twin {proof!r} is missing fixture {fixture_path.name}")
                continue
            fixture = mapping_document(fixture_path, "fixture", errors)
            if fixture is not None:
                fixture_documents[arm] = fixture
        if all(arm in fixture_documents for arm in _ARMS):
            if fixture_documents["columns"] != fixture_documents["document"]:
                errors.append(f"fixture twin {proof!r} does not author equal logical rows")

    cases = compatibility_root / "cases"
    modules = module_ids(compatibility_root, errors)
    case_pairs = _case_pairs(yaml_paths(cases), modules, errors)
    used_descriptors: set[str] = set()
    for key, members in case_pairs.items():
        if any(arm not in members for arm in _ARMS):
            continue
        documents: dict[str, dict[str, Any]] = {}
        model_proofs: dict[str, str] = {}
        for arm in _ARMS:
            path = members[arm]
            case = mapping_document(path, "compatibility case", errors)
            if case is None:
                continue
            documents[arm] = case
            module_tag = primary_module(case, _is_module_tag)
            if module_tag is not None and module_tag not in modules:
                errors.append(
                    f"{path.name}: first module tag {module_tag!r} is not in the "
                    "canonical module catalog"
                )
            elif module_tag != key[0]:
                errors.append(
                    f"{path.name}: filename module {key[0]!r} does not match first "
                    f"module tag {module_tag!r}"
                )
            model = case.get("model")
            model_name = Path(model).name if isinstance(model, str) else ""
            model_match = _MODEL_RE.match(model_name)
            if model_match is None:
                errors.append(f"{path.name}: twin case must reference a twin model descriptor")
                continue
            model_arm = model_match.group("arm")
            model_proof = model_match.group("proof")
            if model_arm != arm:
                errors.append(f"{path.name}: {arm} case references the {model_arm} descriptor arm")
            if model_proof not in descriptor_pairs:
                errors.append(f"{path.name}: references unknown descriptor twin {model_proof!r}")
            model_proofs[arm] = model_proof
        if all(arm in model_proofs for arm in _ARMS):
            if model_proofs["columns"] != model_proofs["document"]:
                errors.append(f"case twin {key!r} references two different descriptor twins")
            else:
                used_descriptors.add(model_proofs["columns"])
        if all(arm in documents for arm in _ARMS):
            if _logical_case(documents["columns"]) != _logical_case(documents["document"]):
                errors.append(f"case twin {key!r} differs in layout-invariant authored behavior")

    for proof in sorted(set(descriptor_pairs) - used_descriptors):
        errors.append(f"descriptor twin {proof!r} is not used by a complete case twin")
    return errors


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
