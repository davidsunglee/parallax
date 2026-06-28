# Create payloads use explicit relationship handling

TypeScript create payloads consume scalar attributes and value objects by default, but nested relationship data must be handled explicitly. `relationships` lists dependent relationship paths to create from the payload, `ignoreRelationships` lists payload relationship paths to ignore, and any remaining nested relationship data is rejected to avoid silent data loss.
