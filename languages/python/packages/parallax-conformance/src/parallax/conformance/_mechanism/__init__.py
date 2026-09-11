"""The mechanism every conformance run lane composes over (``parallax-conformance``, dev-only).

Transaction control, the observation envelope and its error classes, the
model facts and case-document facts a case is read through, and the given-state
seeding. A namespace for navigation rather than a seam: each module states its
own interface, and nothing re-exports through here.
"""

__all__: list[str] = []
