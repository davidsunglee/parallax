"""Shared Snapshot delivery workloads defined by benchmark fixtures."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, Final, Protocol, cast, overload

from parallax.conformance import _case_ingress, case_format, models
from parallax.conformance.budget import BudgetContract
from parallax.core import inheritance, opt_lock, relationship, storage_layout, temporal_read
from parallax.core.entity import DomainModel
from parallax.core.metamodel import Metamodel
from parallax.core.object_query import ObjectQueryNode
from parallax.core.object_query import deserialize as deserialize_query
from parallax.core.object_query._fluent import ObjectQuery, object_query_node

__all__ = ["ScriptedRows", "Workload", "catalog", "workload_digest"]

type RowDocument = Mapping[str, object]
type FixtureRows = Mapping[str, Sequence[RowDocument]]


class Provisioning(Protocol):
    def reset(self, model: Metamodel, fixtures: Mapping[str, object]) -> None: ...


@dataclass(frozen=True, slots=True)
class _GeneratedRows(Sequence[RowDocument]):
    size: int
    row_at: Callable[[int], RowDocument]

    def __len__(self) -> int:
        return self.size

    @overload
    def __getitem__(self, index: int) -> RowDocument: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[RowDocument]: ...

    def __getitem__(self, index: int | slice) -> RowDocument | Sequence[RowDocument]:
        if isinstance(index, slice):
            return tuple(self.row_at(offset) for offset in range(*index.indices(self.size)))
        normalized = index + self.size if index < 0 else index
        if normalized < 0 or normalized >= self.size:
            raise IndexError(index)
        return self.row_at(normalized)

    def __iter__(self) -> Iterator[RowDocument]:
        return (self.row_at(index) for index in range(self.size))


@dataclass(frozen=True, slots=True)
class ScriptedRows:
    """Deterministic logical rows for one provider-free workload arm."""

    entities: FixtureRows
    root_entity: str
    roots: int
    fanout: int

    def entity(self, identity: str) -> Sequence[RowDocument]:
        return self.entities.get(identity, ())


@dataclass(frozen=True, slots=True)
class Workload:
    """One Budget Contract workload backed by one benchmark fixture."""

    id: str
    fixture_path: Path
    document: Mapping[str, object]

    @property
    def page_sizes(self) -> tuple[int, ...]:
        delivery = self.document.get("delivery")
        raw = (
            cast("Mapping[str, object]", delivery).get("pageSizes")
            if isinstance(delivery, Mapping)
            else None
        )
        if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
            raise ValueError(f"{self.fixture_path.name}: delivery.pageSizes is not an array")
        sizes = tuple(cast("Sequence[object]", raw))
        if any(not isinstance(size, int) or isinstance(size, bool) or size < 1 for size in sizes):
            raise ValueError(
                f"{self.fixture_path.name}: delivery.pageSizes must be positive integers"
            )
        return tuple(int(size) for size in cast("Sequence[int]", sizes))

    @property
    def roots(self) -> int:
        generated = self._generated_dataset
        roots = generated.get("rows")
        if not isinstance(roots, int) or isinstance(roots, bool) or roots < 1:
            raise ValueError(f"{self.fixture_path.name}: dataset.generate.rows must be positive")
        return int(roots)

    @property
    def fanout(self) -> int:
        generated = self._generated_dataset
        fanout = generated.get("fanout", 1)
        if not isinstance(fanout, int) or isinstance(fanout, bool) or fanout < 1:
            raise ValueError(f"{self.fixture_path.name}: dataset.generate.fanout must be positive")
        return int(fanout)

    @property
    def _generated_dataset(self) -> Mapping[str, object]:
        dataset = self.document.get("dataset")
        if not isinstance(dataset, Mapping):
            raise ValueError(f"{self.fixture_path.name}: dataset is not a mapping")
        typed_dataset = cast("Mapping[str, object]", dataset)
        generated = typed_dataset.get("generate")
        if not isinstance(generated, Mapping):
            raise ValueError(f"{self.fixture_path.name}: dataset.generate is not a mapping")
        return cast("Mapping[str, object]", generated)

    @property
    def domain_model(self) -> DomainModel:
        return _domain_model(self.model_path)

    @property
    def model(self) -> Metamodel:
        return models.accepted_model_of(self.domain_model)

    @property
    def model_path(self) -> Path:
        reference = self.document.get("model")
        if not isinstance(reference, str):
            raise ValueError(f"{self.fixture_path.name}: model is not a string")
        return self.fixture_path.parent.parent / reference

    @property
    def query(self) -> ObjectQueryNode:
        document = self.document.get("objectQuery")
        if not isinstance(document, Mapping):
            raise ValueError(f"{self.fixture_path.name}: objectQuery is not a mapping")
        return _case_ingress.normalize_case_query(
            deserialize_query(cast("Mapping[str, object]", document)), self.model
        )

    def rows(self, roots: int, *, fanout: int | None = None) -> ScriptedRows:
        if type(roots) is not int or roots < 1:
            raise ValueError("roots must be a positive built-in int")
        dataset = self.document.get("dataset")
        if not isinstance(dataset, Mapping):
            raise ValueError(f"{self.fixture_path.name}: dataset is not a mapping")
        typed_dataset = cast("Mapping[str, object]", dataset)
        generated = typed_dataset.get("generate")
        if isinstance(generated, Mapping):
            typed_generated = cast("Mapping[str, object]", generated)
            recipe = typed_generated.get("recipe")
            selected_fanout = typed_generated.get("fanout", 1) if fanout is None else fanout
            if (
                not isinstance(recipe, str)
                or not isinstance(selected_fanout, int)
                or isinstance(selected_fanout, bool)
                or selected_fanout < 1
            ):
                raise ValueError(f"{self.fixture_path.name}: malformed generated dataset")
            return _generated(recipe, roots, selected_fanout)
        inline = typed_dataset.get("rows")
        if not isinstance(inline, Mapping):
            raise ValueError(f"{self.fixture_path.name}: dataset has no rows or generator")
        entities = {
            str(entity): tuple(cast("RowDocument", row) for row in cast("Sequence[object]", rows))
            for entity, rows in cast("Mapping[object, object]", inline).items()
            if isinstance(rows, Sequence) and not isinstance(rows, str | bytes)
        }
        root_entity = self.query.target.canonical
        available = entities.get(root_entity, ())
        if roots > len(available):
            raise ValueError(
                f"{self.fixture_path.name}: inline dataset has only {len(available)} roots"
            )
        return ScriptedRows(entities, root_entity, roots, 1)

    def validate_class_backed(
        self,
        domain_model: DomainModel,
        query: ObjectQuery[Any, Any] | None = None,
    ) -> None:
        class_model = models.accepted_model_of(domain_model)
        descriptor_model = self.model
        if tuple(class_model.entities) != tuple(descriptor_model.entities):
            raise ValueError(f"{self.id}: class-backed metadata differs from its descriptor")
        class_facets = (
            inheritance.view(class_model),
            relationship.view(class_model),
            storage_layout.view(class_model),
            temporal_read.view(class_model),
            opt_lock.view(class_model),
        )
        descriptor_facets = (
            inheritance.view(descriptor_model),
            relationship.view(descriptor_model),
            storage_layout.view(descriptor_model),
            temporal_read.view(descriptor_model),
            opt_lock.view(descriptor_model),
        )
        for entity in descriptor_model.entities:
            identity = entity.identity
            class_values = (
                class_facets[0].entity(identity),
                class_facets[1].relationships(identity),
                class_facets[2].entity(identity),
                class_facets[3].shape(identity),
                class_facets[4].key(identity),
            )
            descriptor_values = (
                descriptor_facets[0].entity(identity),
                descriptor_facets[1].relationships(identity),
                descriptor_facets[2].entity(identity),
                descriptor_facets[3].shape(identity),
                descriptor_facets[4].key(identity),
            )
            if class_values != descriptor_values:
                raise ValueError(
                    f"{self.id}: class-backed facets differ from its descriptor at "
                    f"{identity.canonical}"
                )
        if query is not None:
            class_query = _case_ingress.normalize_case_query(object_query_node(query), class_model)
            if class_query != self.query:
                raise ValueError(f"{self.id}: class-backed query differs from its fixture")

    def provision(self, database: Provisioning, roots: int) -> None:
        rows = self.rows(roots)
        database.reset(self.model, cast("Mapping[str, object]", rows.entities))


@cache
def _domain_model(path: Path) -> DomainModel:
    return models.load_domain_model(path)


def catalog(contract: BudgetContract | None = None) -> Mapping[str, Workload]:
    return _load_catalog(contract) if contract is not None else _default_catalog()


@cache
def _default_catalog() -> Mapping[str, Workload]:
    return _load_catalog(BudgetContract.load())


def _load_catalog(budget: BudgetContract) -> Mapping[str, Workload]:
    loaded: dict[str, Workload] = {}
    fixture_owners: dict[Path, str] = {}
    for workload_id in budget.workload_ids:
        fixture_path = budget.fixture(workload_id).resolve()
        previous = fixture_owners.get(fixture_path)
        if previous is not None:
            raise ValueError(f"workloads {previous!r} and {workload_id!r} both own {fixture_path}")
        document = case_format.safe_load_yaml(fixture_path.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise ValueError(f"{fixture_path}: benchmark fixture is not a mapping")
        fixture_owners[fixture_path] = workload_id
        loaded[workload_id] = Workload(
            workload_id, fixture_path, cast("Mapping[str, object]", document)
        )
    return loaded


def workload_digest(workloads: Mapping[str, Workload] | None = None) -> str:
    selected = workloads or catalog()
    digest = hashlib.sha256()
    for workload_id, workload in selected.items():
        digest.update(workload_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(workload.fixture_path.read_bytes())
        digest.update(b"\0")
        digest.update(workload.model_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


_ORDER: Final = "parallax.compatibility.Order"
_ITEM: Final = "parallax.compatibility.OrderItem"
_STATUS: Final = "parallax.compatibility.OrderStatus"


def _generated(recipe: str, roots: int, fanout: int) -> ScriptedRows:
    if recipe == "orders-tree":
        return _orders_tree(roots, fanout)
    if recipe == "travelers-tree":
        return _travelers_tree(roots, fanout)
    if recipe == "versioned-documents":
        return _versioned_documents(roots)
    if recipe == "bitemporal-current":
        return _bitemporal_current(roots)
    if recipe == "materialization-stress":
        return _materialization_stress(roots, fanout)
    if recipe == "document-milestones":
        return _document_milestones(roots)
    if recipe == "accounts-sequential":
        accounts = tuple(
            {"id": index, "owner": f"owner-{index}", "balance": f"{index * 100}.00", "version": 1}
            for index in range(1, roots + 1)
        )
        return ScriptedRows(
            {"parallax.compatibility.Account": accounts}, "parallax.compatibility.Account", roots, 1
        )
    raise ValueError(f"unknown benchmark dataset recipe {recipe!r}")


def _orders_tree(roots: int, fanout: int) -> ScriptedRows:
    def order_at(offset: int) -> RowDocument:
        order_id = offset + 1
        return {
            "id": order_id,
            "name": f"order-{order_id:06d}",
            "sku": "A-100",
            "qty": 5,
            "price": Decimal("10.50"),
            "active": True,
            "orderedOn": "2024-01-05",
        }

    def item_at(offset: int) -> RowDocument:
        item_id = offset + 1
        return {
            "id": item_id,
            "orderId": offset // fanout + 1,
            "sku": "SKU",
            "quantity": 1,
            "shippedOn": "2024-02-01",
        }

    def status_at(offset: int) -> RowDocument:
        status_id = offset + 1
        item_offset = offset // fanout
        return {
            "id": status_id,
            "orderId": item_offset // fanout + 1,
            "orderItemId": item_offset + 1,
            "code": "OPEN",
        }

    return ScriptedRows(
        {
            _ORDER: _GeneratedRows(roots, order_at),
            _ITEM: _GeneratedRows(roots * fanout, item_at),
            _STATUS: _GeneratedRows(roots * fanout * fanout, status_at),
        },
        _ORDER,
        roots,
        fanout,
    )


def _travelers_tree(roots: int, fanout: int) -> ScriptedRows:
    travelers = tuple(
        {
            "id": index,
            "displayName": f"traveler-{index}",
            "score": index,
            "joinedOn": "2026-01-15",
            "note": f"note-{index}",
            "address": {"city": "Oslo", "geo": {"country": "NO"}},
            "tags": [{"label": f"tag-{offset}"} for offset in range(fanout)],
        }
        for index in range(1, roots + 1)
    )
    trips = tuple(
        {
            "id": (index - 1) * fanout + offset + 1,
            "travelerId": index,
            "destination": f"destination-{offset}",
            "nights": offset + 1,
        }
        for index in range(1, roots + 1)
        for offset in range(fanout)
    )
    return ScriptedRows(
        {
            "parallax.compatibility.Traveler": travelers,
            "parallax.compatibility.Trip": trips,
        },
        "parallax.compatibility.Traveler",
        roots,
        fanout,
    )


def _versioned_documents(roots: int) -> ScriptedRows:
    rows = tuple(
        {
            "id": index,
            "version": 1,
            "label": f"ledger-{index}",
            "balance": "10.00",
            "details": {"code": "OPEN"},
        }
        for index in range(1, roots + 1)
    )
    entity = "parallax.compatibility.Ledger"
    return ScriptedRows({entity: rows}, entity, roots, 1)


def _bitemporal_current(roots: int) -> ScriptedRows:
    rows = tuple(
        {
            "id": index,
            "route": f"route-{index}",
            "terms": {"clause": "standard"},
            "validStart": "2026-01-01T00:00:00+00:00",
            "validEnd": "infinity",
            "txStart": "2026-01-01T00:00:00+00:00",
            "txEnd": "infinity",
        }
        for index in range(1, roots + 1)
    )
    entity = "parallax.compatibility.Charter"
    return ScriptedRows({entity: rows}, entity, roots, 1)


def _document_milestones(roots: int) -> ScriptedRows:
    voyages = tuple(
        {
            "id": index,
            "title": f"voyage-{index}",
            "crew": 4,
            "manifest": {"cargo": "timber"},
            "txStart": "2026-01-01T00:00:00+00:00",
            "txEnd": "infinity",
        }
        for index in range(1, roots + 1)
    )
    chartered = _bitemporal_current(roots).entities["parallax.compatibility.Charter"]
    return ScriptedRows(
        {
            "parallax.compatibility.Voyage": voyages,
            "parallax.compatibility.Charter": chartered,
        },
        "parallax.compatibility.Voyage",
        roots,
        1,
    )


def _materialization_stress(roots: int, fanout: int) -> ScriptedRows:
    owners: list[RowDocument] = []
    alpha: list[RowDocument] = []
    beta: list[RowDocument] = []
    for index in range(roots):
        owner_id = 1_000 + index
        favorite = 10_000 + index * 10
        owners.append({"id": owner_id, "name": f"owner-{index}", "favoriteId": favorite})
        for offset in range(fanout):
            row: RowDocument = {
                "id": favorite + offset,
                "ownerId": owner_id,
                "label": f"node-{index}-{offset}",
                "tags": [],
            }
            (alpha if offset < 2 else beta).append(row)
    return ScriptedRows(
        {
            "snapshot.materialization.Owner": tuple(owners),
            "snapshot.materialization.Alpha": tuple(alpha),
            "snapshot.materialization.Beta": tuple(beta),
        },
        "snapshot.materialization.Owner",
        roots,
        fanout,
    )
