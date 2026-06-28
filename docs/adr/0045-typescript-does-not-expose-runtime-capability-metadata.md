# TypeScript does not expose runtime capability metadata

The TypeScript generated API does not expose runtime capability metadata in V1. Application code should rely on generated types, package versions, documentation, and conformance results rather than branching on a runtime capability object.

Conformance remains an external verification concern. The compatibility harness, CI, and optional diagnostic commands may report which core slices an implementation passes, but that metadata is not part of the everyday `#parallax` domain API.
