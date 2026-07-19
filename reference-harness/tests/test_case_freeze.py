"""The parsed compatibility corpus is deeply immutable, cached, and safely shared.

``discover_cases``/``load_case``/``load_model`` hand every caller the *same*
parsed graph. That is only sound because the graph rejects writes: before the
freeze, per-call re-parsing was the sole thing isolating the corruption tests
from one another, an implicit contract that nothing stated and nothing enforced.

These tests pin the contract itself — that a write raises, that the freeze
reaches aliased inner nodes, that ``copy.deepcopy`` remains the sanctioned way
out, and that the corpus is parsed at most once per resolved root per process.
They are the guard rail that makes sharing one parsed graph between callers safe
rather than merely fast.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

import reference_harness.case as case_module
from reference_harness.case import discover_cases, load_case, load_model
from reference_harness.inheritance import resolve_effective_definition

COMPATIBILITY_ROOT = Path(__file__).resolve().parents[2] / "core" / "compatibility"


def _any_case():
    """One arbitrary parsed case — the contract is graph-wide, not case-specific."""
    return discover_cases(COMPATIBILITY_ROOT)[0]


def test_case_raw_rejects_item_assignment() -> None:
    case = _any_case()
    with pytest.raises(TypeError):
        case.raw["model"] = "models/hacked.yaml"


def test_case_raw_rejects_key_deletion() -> None:
    case = _any_case()
    with pytest.raises(TypeError):
        del case.raw["model"]


def test_nested_case_document_rejects_item_assignment() -> None:
    """The freeze is recursive — an inner node is as immutable as the root."""
    case = next(c for c in discover_cases(COMPATIBILITY_ROOT) if c.when)
    with pytest.raises(TypeError):
        case.when["injected"] = True


def test_model_descriptor_attribute_list_rejects_append() -> None:
    """Sequence nodes reject in-place growth, not just mapping nodes."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    attributes = model.descriptor["entities"][0]["attributes"]
    with pytest.raises(TypeError):
        attributes.append({"name": "injected", "type": "string", "column": "injected"})


def test_model_fixtures_reject_mutation() -> None:
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    with pytest.raises(TypeError):
        model.fixtures["injected"] = []


def test_inheritance_effective_definition_alias_stays_frozen() -> None:
    """The alias `_merge_ancestry_attributes` splices in must not be a side door.

    That helper appends the *original* ancestor attribute dicts into the list it
    returns rather than copies of them, so a shallow freeze would leave an
    inheritance participant's inherited attributes writable through the flattened
    definition — corrupting the ancestor for every later reader of the shared
    graph. The returned list is itself a fresh, mutable list; it is the elements
    that must stay frozen.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    resolved = resolve_effective_definition(list(model.descriptor["entities"]), "CardPayment")
    inherited = next(a for a in resolved["attributes"] if a["name"] == "amount")
    with pytest.raises(TypeError):
        inherited["column"] = "hijacked"


def test_deepcopy_yields_a_fully_mutable_graph() -> None:
    """The sanctioned escape hatch: negative tests build malformed input this way."""
    case = copy.deepcopy(_any_case())
    case.raw["model"] = "models/damaged.yaml"
    assert case.raw["model"] == "models/damaged.yaml"


def test_deepcopy_does_not_disturb_the_shared_original() -> None:
    original = _any_case()
    before = original.raw["model"]
    damaged = copy.deepcopy(original)
    damaged.raw["model"] = "models/damaged.yaml"
    assert _any_case().raw["model"] == before


def test_frozen_nodes_are_still_dict_and_list_instances() -> None:
    """Load-bearing: ~176 `isinstance(x, dict)`/`isinstance(x, list)` shape checks
    across the harness (schema_validate, sql_lint, inheritance, case_runner, …)
    must keep seeing corpus documents as the builtins they are. Freezing to
    `MappingProxyType`/`tuple` would fail every one of them silently, turning an
    immutability change into a behavior change.
    """
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    assert isinstance(model.descriptor, dict)
    assert isinstance(model.descriptor["entities"], list)
    assert isinstance(model.descriptor["entities"][0], dict)
    assert isinstance(model.descriptor["entities"][0]["attributes"], list)


def test_frozen_nodes_compare_equal_to_plain_literals() -> None:
    """Equality against plain `dict`/`list` literals is what the assertions in the
    existing suite are written against; the freeze must not disturb it."""
    model = load_model(COMPATIBILITY_ROOT, "models/payment.yaml")
    entity = model.descriptor["entities"][0]
    assert entity["inheritance"] == dict(entity["inheritance"])
    assert entity["attributes"] == list(entity["attributes"])


# --------------------------------------------------------------------------
# Parse-once: the payoff the freeze exists to make safe.
# --------------------------------------------------------------------------


@pytest.fixture
def yaml_reads(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every YAML file the loaders actually open.

    Counting reads is the only honest measure here: a wall-clock or call-count
    assertion on ``discover_cases`` itself would still pass if the cache were
    silently removed.
    """
    reads: list[Path] = []
    real_load_yaml = case_module._load_yaml  # noqa: SLF001

    def counting_load_yaml(path: Path) -> Any:
        reads.append(path)
        return real_load_yaml(path)

    monkeypatch.setattr(case_module, "_load_yaml", counting_load_yaml)
    return reads


def _write_throwaway_corpus(root: Path) -> None:
    """The smallest tree ``discover_cases`` accepts: one case, one model, fixtures.

    Deliberately *not* the shared corpus — a fresh ``tmp_path`` root has never
    been parsed in this process, so the cold-parse half of the assertion below is
    real rather than an artifact of test ordering.
    """
    (root / "cases").mkdir(parents=True)
    (root / "models").mkdir()
    (root / "fixtures").mkdir()
    (root / "cases" / "tiny-001.yaml").write_text(
        "id: tiny-001\nmodel: models/tiny.yaml\n", encoding="utf-8"
    )
    (root / "models" / "tiny.yaml").write_text(
        "entity:\n  class: Tiny\n  table: tiny\n  attributes: []\n", encoding="utf-8"
    )
    (root / "fixtures" / "tiny.yaml").write_text("Tiny: []\n", encoding="utf-8")


def test_a_second_discovery_of_the_same_root_reads_nothing(
    tmp_path: Path, yaml_reads: list[Path]
) -> None:
    """One full corpus parse per root per process — the whole point of the cache.

    Before this, ``discover_cases`` opened 1,186 files over a 463-file corpus on
    *every* call, from ~40 call sites in this suite.
    """
    _write_throwaway_corpus(tmp_path)

    first = discover_cases(tmp_path)
    assert yaml_reads, "the first discovery of an unseen root must actually parse it"

    yaml_reads.clear()
    second = discover_cases(tmp_path)
    assert yaml_reads == []

    assert [c.path for c in second] == [c.path for c in first]


def test_the_shared_corpus_is_parsed_at_most_once_per_process(yaml_reads: list[Path]) -> None:
    """The real corpus, exercised the way every harness module reaches it."""
    discover_cases(COMPATIBILITY_ROOT)
    yaml_reads.clear()

    cases = discover_cases(COMPATIBILITY_ROOT)

    assert yaml_reads == []
    assert cases, "the shared corpus must still be discovered, not merely cached empty"


def test_an_unresolved_spelling_of_a_root_does_not_reparse(yaml_reads: list[Path]) -> None:
    """The cache keys on ``.resolve()``, so an equivalent spelling is one entry.

    Every test module spells the root as a fixed-depth ``parents[2]`` walk, but a
    CLI caller passes whatever was on the command line; keying on the raw path
    would hand a second full parse to a ``..``-containing or symlinked spelling of
    the very same directory.
    """
    discover_cases(COMPATIBILITY_ROOT)
    yaml_reads.clear()

    detoured = COMPATIBILITY_ROOT / "cases" / ".."

    assert discover_cases(detoured)
    assert load_model(detoured, "models/payment.yaml").descriptor
    assert yaml_reads == []


def test_repeat_load_case_and_load_model_read_nothing(yaml_reads: list[Path]) -> None:
    """The per-artifact loaders memoize too — ``load_model`` is the ~11.8× read."""
    case = discover_cases(COMPATIBILITY_ROOT)[0]
    yaml_reads.clear()

    assert load_case(COMPATIBILITY_ROOT, case.path) is case
    assert load_model(COMPATIBILITY_ROOT, case.raw["model"]) is case.model
    assert yaml_reads == []


def test_two_requested_collections_cannot_contaminate_each_other() -> None:
    """The isolation the cache must preserve, stated end to end.

    Two callers now genuinely share one graph, so isolation can no longer come
    from re-parsing. It comes from the freeze: the only way to damage a case is
    to deep-copy it first, and a copy is by construction detached from the
    template every other caller holds.
    """
    collection_a = discover_cases(COMPATIBILITY_ROOT)
    collection_b = discover_cases(COMPATIBILITY_ROOT)

    target = next(c for c in collection_a if c.when)
    pristine = dict(target.when)

    with pytest.raises(TypeError):
        target.when["injected"] = True

    damaged = copy.deepcopy(target)
    damaged.raw["model"] = "models/damaged.yaml"
    damaged.when["injected"] = True

    peer = next(c for c in collection_b if c.path == target.path)
    assert peer.raw["model"] == target.raw["model"] != "models/damaged.yaml"
    assert dict(peer.when) == pristine
    assert "injected" not in peer.when


def test_discovery_hands_each_caller_its_own_list() -> None:
    """The list is the one mutable thing a caller gets, and it is per-call.

    Callers filter and re-sort what ``discover_cases`` returns; sharing the list
    object itself would reintroduce exactly the cross-test contamination the
    freeze removes.
    """
    first = discover_cases(COMPATIBILITY_ROOT)
    second = discover_cases(COMPATIBILITY_ROOT)

    assert first is not second
    first.clear()
    assert second, "one caller emptying its list must not empty another's"
