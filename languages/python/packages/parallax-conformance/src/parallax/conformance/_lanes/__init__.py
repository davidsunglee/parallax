"""The run lanes of the conformance engine (``parallax-conformance``, dev-only).

One module per lane: each takes a case and, where the lane reaches a database,
a port, composes over :mod:`~parallax.conformance._mechanism`, and returns the
observation the adapter grades against the case's ``then``. A namespace for
navigation rather than a seam: each lane states its own interface, and nothing
re-exports through here.
"""

__all__: list[str] = []
