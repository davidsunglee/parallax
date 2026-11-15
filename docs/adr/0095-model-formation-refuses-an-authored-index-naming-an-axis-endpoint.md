# Model Formation refuses an authored index naming an axis endpoint

An authored index component that is one of its Entity's own As-Of Axis start or
end Attributes is now refused by Model Formation, as
`metamodel-index-temporal-attribute` (`m-metamodel`), for every frontend. It
replaces the descriptor's value-phase rejection `index-temporal-attribute`,
which [ADR 0050](0050-primary-key-index-is-derived.md) and
[ADR 0052](0052-temporality-profile-is-authored-and-axes-are-derived.md)
recorded; their reasons for refusing such a component stand, and
[ADR 0081](0081-authored-indices-on-temporal-tables-end-with-the-axis-ends.md)'s
restatement of them, that every index already ends with the derived axis ends,
is the reason now.

The descriptor was the only place the rule lived. The Python class frontend
resolves an index component by name to the derived endpoint Attribute and never
refused it, so `index("price_audit", "sku", "valid_end", "tx_end")` on a
Bitemporal class provisioned an index ending `thru_z, out_z`: a shape the
contract does not admit, and one
[ADR 0094](0094-indices-on-bitemporal-tables-end-with-the-transaction-time-end-first.md)
leaves to an operator's own migrations.

The rule depends only on one declaration's authored indices and axes, which
every frontend already hands Model Formation, beside the other index-component
rules. Stated there once, it holds whatever authored the model, the corpus
proves it with a rejected case, and the reference harness checks it
independently. The derived primary-key index is not authored, so its end
components are not refused.

Keeping the descriptor's rejection beside it, as the endpoint-name reservation
keeps `temporal-attribute-declared` beside `metamodel-temporal-member-reserved`,
was rejected. A descriptor would be judged twice, no corpus case could reach the
formation rule through a descriptor, and the descriptor's error added only a
document path, which a frontend may map back from a Model Location. A check in
the Python class frontend alone was rejected for leaving the rule outside the
core. A descriptor naming an endpoint in an index now fails Model Formation, at
the index's location, rather than the value phase at the component's path.
