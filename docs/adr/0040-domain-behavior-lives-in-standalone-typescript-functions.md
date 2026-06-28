# Domain behavior lives in standalone TypeScript functions

Generated TypeScript domain objects are managed data and relationship surfaces, not user extension points. Application-specific behavior should live in ordinary TypeScript modules as standalone functions that accept generated objects, snapshots, `Parallax`, or `ParallaxTransaction` as parameters.

Generated Parallax files are inspectable but not editable. The generator owns its output and may overwrite it during install, build, or CI. Customization belongs in descriptors, generator configuration, runtime adapters, and application-owned domain functions rather than edits to generated files or subclasses of generated objects.
