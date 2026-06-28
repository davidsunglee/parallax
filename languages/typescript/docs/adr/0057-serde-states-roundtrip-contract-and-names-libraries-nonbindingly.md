# Serde states the round-trip contract and names libraries non-bindingly

The spec states the *contract* the canonical serde module must satisfy and names concrete libraries only as a non-binding suggested default. The contract is the durable, normative requirement; the dependencies that implement it are replaceable.

The contract has four parts, transcribed from the Python harness's `serde.py` so the TypeScript seam canonicalizes identically to the oracle:

- **Safe load.** Deserialization uses a safe loader that never constructs arbitrary types from input (the YAML analogue of `yaml.safe_load`; built-in `JSON.parse` is already safe).
- **Deterministic recursive key sort.** `canonical(value)` sorts object keys recursively so semantically equal values serialize to the same text.
- **List-order preservation.** Array order is preserved (never sorted), because order is significant in both the operation algebra and attribute/row sequences.
- **Lossless round-trip in both formats.** `assertRoundTrip(value)` runs JSON and YAML and asserts, in each, that serialization is idempotent (a fixed point) and that re-parsing canonicalizes back to the same value (no data loss).

The suggested-but-non-binding default is the `yaml` package (or `js-yaml`) for the YAML writer plus built-in `JSON` for JSON, with the canonicalizer written in-house exactly as the Python harness writes its own `_canonicalize`. Naming concrete libraries normatively was rejected because it couples a normative spec to a swappable dependency; an implementer may satisfy the contract with any library that honors safe load, deterministic key sort, list-order preservation, and lossless JSON+YAML round-trip.
