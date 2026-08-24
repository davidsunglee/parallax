# Compact Pydantic state uses a framework-owned core-schema seam

Published compact Entity and Value Object instances remain instances of the
user's actual Pydantic class, so their alternate backing must compose with
Pydantic's compiled serializer and every supported authored serializer without
changing the object those extensions observe. Parallax therefore owns the
inherited `BaseModel.__get_pydantic_core_schema__` hook and integrates compact
state through a public `pydantic_core.core_schema` wrap serializer isolated
inside the private instance-state Module. Entity and Value Object declarations
reserve that exact hook name; other supported Pydantic extension points remain
authored behavior.

The integration must serialize the original instance directly. A transient
ordinary same-class proxy was rejected because instance-bound serializers and
computed fields observe the proxy as `self`; temporarily populating the compact
object's ordinary Pydantic state was rejected because it mutates shared frozen
state and adds allocation and exception-restoration hazards; replacing the
compiled serializer by hand was rejected because it would have to reproduce
Pydantic's evolving composition rules. The direct proof must preserve authored
extensions and JSON Schema output on the minimum and locked/latest supported
Pydantic releases before the broad backing rewrite begins. If that proof fails,
the work stops for evidence-backed review rather than weakening compatibility.
