# Generated TypeScript API uses a package import alias

Application code imports the generated Parallax API through a package-style alias rather than deep relative paths. The preferred alias is `#parallax`, backed by the project's resolver configuration and generated output path. This keeps imports stable when files move and makes the generated API feel like a coherent local module.

`#parallax` is preferred over names such as `@app/parallax` because package import specifiers beginning with `#` are private to the current package and are not confused with external package names. A scoped package-style alias may still be supported for projects whose tooling already standardizes on that convention, but it is not the default.

The trade-off is setup complexity. TypeScript, runtime, test, and bundler resolution must agree on the alias before typechecking and execution. Parallax should make this boring through `parallax init`, generated setup guidance, and a generation check that validates the configured alias resolves to the generated API.
