# Snapshots are the TypeScript detached data surface

TypeScript uses domain snapshots as the idiomatic detached-data representation for REST, UI editing, messaging, and later merge workflows. Reladomo-style detached Parallax objects are not part of the first public TypeScript API; future M9 merge-back behavior should be expressed through explicit snapshot apply or merge APIs that preserve the core observable semantics.
