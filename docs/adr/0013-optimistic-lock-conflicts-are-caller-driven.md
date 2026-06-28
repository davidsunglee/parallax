# Optimistic lock conflicts are caller-driven

Parallax reports optimistic lock conflicts instead of automatically retrying them. Callers usually need to inspect the winning change and decide whether their pending change still makes sense.
