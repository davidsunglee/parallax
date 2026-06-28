# Exported runtime types use the Parallax prefix

Exported runtime infrastructure types and package-owned errors use the `Parallax` prefix, such as `ParallaxList`, `ParallaxError`, and `ParallaxTooManyResultsError`. The shorter `px` name is reserved for conventional local variables, keeping everyday code compact while preserving clear names in imports, stack traces, and logs.
