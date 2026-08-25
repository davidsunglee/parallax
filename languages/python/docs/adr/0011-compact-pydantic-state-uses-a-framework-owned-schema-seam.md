# Compact Pydantic state uses a framework-owned core-schema seam

Published compact Entity and Value Object instances remain instances of the
user's actual Pydantic class, so their alternate backing must compose with
Pydantic's compiled serializer and every supported authored serializer without
changing the object those extensions observe. Parallax therefore owns the
inherited `BaseModel.__get_pydantic_core_schema__` hook, isolated inside the
private instance-state Module. Behind it the validation schema is left
untouched and the model schema is given a serialization-only schema whose
fields are computed, because the compiled serializer sources declared fields
from physical state and computed fields by attribute; one schema then serves
compact and ordinary backing alike. Entity and Value Object declarations
reserve that exact hook name; other supported Pydantic extension points remain
authored behavior.

The integration must serialize the original instance directly. A transient
ordinary same-class proxy was rejected because instance-bound serializers and
computed fields observe the proxy as `self`; temporarily populating the compact
object's ordinary Pydantic state was rejected because it mutates shared frozen
state and adds allocation and exception-restoration hazards; replacing the
compiled serializer by hand was rejected because it would have to reproduce
Pydantic's evolving composition rules; a `core_schema` wrap serializer was
rejected on evidence, because field serialization needs the model context only
the model serializer establishes and that serializer reads the instance
dictionary, so no wrap handler can be fed compact values. The direct proof must
preserve authored extensions and JSON Schema output on the minimum and
locked/latest supported Pydantic releases before the broad backing rewrite
begins. If that proof fails, the work stops for evidence-backed review rather
than weakening compatibility.

Holding JSON Schema unchanged needs a second framework-owned hook,
`__get_pydantic_json_schema__` on the Entity and Value Object roots, because a
computed field is always required in serialization mode. That hook is owned but
not reserved, so authored JSON-schema customization keeps working. Carrying the
same correction in core-schema metadata would have kept Parallax to one hook and
was rejected because the key it needs is private to Pydantic.
