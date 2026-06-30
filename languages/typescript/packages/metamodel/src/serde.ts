/**
 * Descriptor serde, routed through the shared `@parallax/serde` seam.
 *
 * The metamodel and the operation algebra canonicalize through the *same* serde
 * seam (M1 §"Metamodel serde"; ADR-0056), so descriptor and operation encodings
 * canonicalize identically to the Python oracle. This module is the metamodel
 * side of that seam: `serialize(deserialize(descriptor)) == descriptor` must
 * hold in both JSON and YAML for every model a case references.
 */
import {
  assertRoundTrip,
  canonical,
  deserialize,
  type SerdeFormat,
  serialize,
} from "@parallax/serde";

/** Parse a model descriptor from canonical JSON or YAML text. */
export function deserializeDescriptor(text: string, format: SerdeFormat = "yaml"): unknown {
  return deserialize(text, format);
}

/** Serialize a model descriptor to canonical JSON or YAML text. */
export function serializeDescriptor(descriptor: unknown, format: SerdeFormat = "yaml"): string {
  return serialize(descriptor, format);
}

/** Canonicalize a descriptor (recursive key-sort; array order preserved). */
export function canonicalDescriptor(descriptor: unknown): unknown {
  return canonical(descriptor);
}

/**
 * Assert the descriptor round-trips losslessly through JSON and YAML — the M1
 * serde contract, proven for every model referenced by a compatibility case.
 */
export function assertDescriptorRoundTrip(descriptor: unknown): void {
  assertRoundTrip(descriptor);
}
