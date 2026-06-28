# TypeScript uses one fluent expression DSL

The TypeScript API uses one generated, type-safe fluent expression DSL for predicates and assignments instead of supporting both Prisma-style object filters and expression-builder filters. This keeps autocomplete strong, avoids two query languages, and maps directly to the canonical Parallax operation algebra.
