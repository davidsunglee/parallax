"""Every corpus model this package mirrors as Entity Classes, by model stem.

One Domain Model per corpus model, so a story or example that names its model as
a string reaches the classes for it without naming the module they live in. Each
model is composed once, where its classes are declared — not because a class
could not participate in a second Domain Model, which it may, but because one
composition per corpus model is what makes this mapping a correspondence rather
than a choice.

The mapping is not a registry — nothing registers into it, and importing a class
adds nothing. It is the fixed correspondence between the corpus's own model files
and the class families this package hand-authors against them.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from parallax.conformance.animal_owner import ANIMAL_MODEL
from parallax.conformance.graph_models import POLICY_MODEL
from parallax.conformance.read_models import (
    BALANCE_MODEL,
    DOCUMENT_MODEL,
    PAYMENT_MODEL,
    PERSON_MODEL,
    RATE_MODEL,
)
from parallax.conformance.story_models import (
    ACCOUNT_MODEL,
    ORDERS_MODEL,
    POSITION_MODEL,
    WALLET_MODEL,
)
from parallax.conformance.vo_models import (
    BRANCH_MODEL,
    CONTACT_MODEL,
    CUSTOMER_MODEL,
    SHIPMENT_MODEL,
    SUPPLIER_MODEL,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from parallax.core import DomainModel

__all__ = ["MODELS"]

MODELS: Mapping[str, DomainModel] = MappingProxyType(
    {
        "account": ACCOUNT_MODEL,
        "animal": ANIMAL_MODEL,
        "balance": BALANCE_MODEL,
        "branch": BRANCH_MODEL,
        "contact": CONTACT_MODEL,
        "customer": CUSTOMER_MODEL,
        "document": DOCUMENT_MODEL,
        "orders": ORDERS_MODEL,
        "payment": PAYMENT_MODEL,
        "person": PERSON_MODEL,
        "policy": POLICY_MODEL,
        "position": POSITION_MODEL,
        "rate": RATE_MODEL,
        "shipment": SHIPMENT_MODEL,
        "supplier": SUPPLIER_MODEL,
        "wallet": WALLET_MODEL,
    }
)
"""Corpus model stem -> the Domain Model its idiomatic classes compose into."""
