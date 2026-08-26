"""The schema adaptation the Azure dialect needs.

Strict structured-output modes want every object to forbid extra properties
and to list every property as required — including optional ones, which
carry a null branch in their type. Pydantic emits the first and not the
second. This walk closes the gap. It was written inside the Azure provider
as provider-shaped work and moved here when the third provider seemed to
need it; that provider's dialect turned out to want a different adaptation
— its vendor's own transform — so this one serves Azure alone for now, and
stays shared in case a fourth dialect wants it. See ``docs/DECISIONS.md``.
"""

from __future__ import annotations

import json
from typing import Any


def close_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a Pydantic JSON Schema with every object closed."""
    adapted = json.loads(json.dumps(schema))
    _close_object(adapted)
    for definition in (adapted.get("$defs") or {}).values():
        _close_object(definition)
    return adapted


def _close_object(node: Any) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties") or {}
        node["additionalProperties"] = False
        node["required"] = list(properties)
        for child in properties.values():
            _close_object(child)
    for key in ("items", "prefixItems"):
        child = node.get(key)
        if isinstance(child, list):
            for item in child:
                _close_object(item)
        elif child is not None:
            _close_object(child)
    for key in ("anyOf", "oneOf", "allOf"):
        for item in node.get(key) or []:
            _close_object(item)
