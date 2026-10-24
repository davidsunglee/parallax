# Python architecture

These pages show how the Python implementation is built: which types and modules a
flow passes through, and where each stage happens. They are maps of the current code,
not contracts. The [core specification](../../../../core/spec/00-overview.md) and the
[Python binding](../../spec/python.md) own behaviour, and the
[concept pages](../../../../docs/concepts/README.md) explain the same flows in domain
terms.

- [Read flow](read-flow.md): from `db.find`, `db.stream`, `db.read_only` or `db.transact`
  through the shared gate, planning, SQL and Page assembly to Typed or Wire values, and
  where eager and streamed delivery part ways.
