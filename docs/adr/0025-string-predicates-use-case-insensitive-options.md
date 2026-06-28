# String predicates use case-insensitive options

TypeScript string predicates accept an options object for case-insensitive matching rather than exposing separate insensitive method names. This keeps the attribute method surface compact while preserving the core operation's `caseInsensitive` flag.
