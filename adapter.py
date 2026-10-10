"""Deterministic schema adapter. It builds payloads but executes no actions."""

from datetime import date, datetime
import json
import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
QUOTED_RE = re.compile(r"[\"']([^\"']+)[\"']")


def read_schema(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a simple field description list from JSON Schema or shorthand."""
    if not isinstance(schema, dict):
        raise TypeError("schema must be a dictionary")
    if "properties" in schema:
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            raise ValueError("schema properties must be a dictionary")
        required = set(schema.get("required", []))
    else:
        properties = schema
        required = set(properties)

    fields = []
    for name, definition in properties.items():
        field_type, allowed, format_name = _parse_definition(definition)
        fields.append({
            "name": name, "type": field_type, "required": name in required,
            "enum": allowed, "format": format_name,
        })
    return fields


def _parse_definition(definition: Any) -> tuple[str, list[Any] | None, str | None]:
    if isinstance(definition, dict):
        if not definition:
            return "object", None, None
        return definition.get("type", "string"), definition.get("enum"), definition.get("format")
    if not isinstance(definition, str):
        raise ValueError("field definitions must be strings or dictionaries")
    text = definition.strip()
    if text == "{}":
        return "object", None, None
    if text == "[]":
        return "array", None, None
    if text.lower() == "yyyy-mm-dd":
        return "string", None, "date"
    if "|" in text:
        return "string", [item.strip() for item in text.split("|")], None
    return text.lower(), None, None


def _extract_from_dict(input_data: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    lower_keys = {str(key).lower(): key for key in input_data}
    for field in fields:
        name = field["name"]
        if name in input_data:
            result[name] = input_data[name]
        elif name.lower() in lower_keys:
            result[name] = input_data[lower_keys[name.lower()]]
    return result


def _extract_from_text(text: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    email_match = EMAIL_RE.search(text)
    quoted = QUOTED_RE.findall(text)
    for field in fields:
        name = field["name"]
        lowered = name.lower()
        explicit = _extract_labeled_value(text, name)
        if explicit is not None:
            result[name] = explicit
            continue
        enum_value = _extract_enum(text, field.get("enum"))
        if enum_value is not None:
            result[name] = enum_value
        elif any(word in lowered for word in ("email", "recipient")) and email_match:
            result[name] = email_match.group(0)
        elif any(word in lowered for word in ("title", "subject", "task_name", "event_name")) and quoted:
            result[name] = quoted[0]
        elif field["type"] == "object":
            object_value = _extract_json_object(text, name)
            if object_value is not None:
                result[name] = object_value
    return result


def _extract_labeled_value(text: str, field_name: str) -> str | None:
    label = re.escape(field_name).replace("_", r"[ _]")
    match = re.search(rf"\b{label}\s*(?:is|=|:)\s*[\"']?([^,;.\n\"']+)", text, re.I)
    return match.group(1).strip() if match else None


def _extract_enum(text: str, allowed: list[Any] | None) -> Any | None:
    if not allowed:
        return None
    for value in allowed:
        if re.search(rf"\b{re.escape(str(value))}\b", text, re.I):
            return value
    return None


def _extract_json_object(text: str, field_name: str) -> dict[str, Any] | None:
    label = re.escape(field_name).replace("_", r"[ _]")
    match = re.search(rf"\b{label}\s*(?:is|=|:)\s*(\{{[^\n]*?\}})", text, re.I)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _result_envelope(
    payload: dict[str, Any] | None,
    missing: list[str],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    if missing or issues:
        return {
            "status": "needs_clarification",
            "payload": None,
            "missing": missing,
            "issues": issues,
        }
    return {"status": "ok", "payload": payload, "missing": [], "issues": []}


def adapt(
    input_data: dict[str, Any] | str,
    schema: dict[str, Any],
    reference_date: date | datetime | str | None = None,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """Extract, normalize, and validate data against a receiving contract."""
    fields = read_schema(schema)
    if isinstance(input_data, dict):
        extracted = _extract_from_dict(input_data, fields)
    elif isinstance(input_data, str):
        extracted = _extract_from_text(input_data, fields)
    else:
        raise TypeError("input_data must be a dictionary or string")
    return _result_envelope(extracted, [], [])
