"""Deterministic schema adapter. It builds payloads but executes no actions."""

from datetime import date, datetime, timedelta, timezone as datetime_timezone
import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
TIME_RE = re.compile(r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\b", re.I)
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
        allowed = definition.get("enum")
        field_type = definition.get("type")
        if field_type is None and allowed:
            field_type = _python_value_type(allowed[0])
        return field_type or "string", allowed, definition.get("format")

    if not isinstance(definition, str):
        raise ValueError("field definitions must be strings or dictionaries")

    text = definition.strip()
    lowered = text.lower()
    known_types = {"string", "integer", "number", "boolean", "object", "array", "null"}
    if lowered in known_types:
        return lowered, None, None
    if text == "{}":
        return "object", None, None
    if text == "[]":
        return "array", None, None
    if lowered == "yyyy-mm-dd":
        return "string", None, "date"
    if "|" in text:
        return "string", [item.strip() for item in text.split("|")], None
    return "string", None, None
def adapt(
    input_data: dict[str, Any] | str,
    schema: dict[str, Any],
    reference_date: date | datetime | str | None = None,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """Extract, normalize, and validate data against a receiving contract."""
    fields = read_schema(schema)
    reference, setup_issues = _resolve_reference_date(reference_date, timezone)

    if isinstance(input_data, dict):
        extracted = _extract_from_dict(input_data, fields)
    elif isinstance(input_data, str):
        extracted = _extract_from_text(input_data, fields, reference, timezone)
    else:
        raise TypeError("input_data must be a dictionary or string")

    normalized = {}
    normalization_issues = []
    for field in fields:
        name = field["name"]
        if name not in extracted:
            continue
        value, error = _normalize_value(extracted[name], field, reference, timezone)
        if error:
            normalization_issues.append({"field": name, "message": error})
        else:
            normalized[name] = value

    missing, validation_issues = _validate(normalized, fields)
    issues = setup_issues + normalization_issues + validation_issues
    if missing or issues:
        return {
            "status": "needs_clarification",
            "payload": None,
            "missing": missing,
            "issues": issues,
        }
    return {"status": "ok", "payload": normalized, "missing": [], "issues": []}
def _resolve_reference_date(
    value: date | datetime | str | None, timezone_name: str
) -> tuple[date, list[dict[str, str]]]:
    issues = []
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = datetime_timezone.utc
        issues.append({"field": "timezone", "message": f"Unknown timezone: {timezone_name}"})

    if value is None:
        return datetime.now(zone).date(), issues
    if isinstance(value, datetime):
        return value.date(), issues
    if isinstance(value, date):
        return value, issues
    if isinstance(value, str):
        try:
            return date.fromisoformat(value), issues
        except ValueError:
            issues.append({"field": "reference_date", "message": "reference_date must use YYYY-MM-DD"})
            return datetime.now(zone).date(), issues
    raise TypeError("reference_date must be a date, datetime, ISO date string, or None")
def _extract_from_dict(
    input_data: dict[str, Any], fields: list[dict[str, Any]]
) -> dict[str, Any]:
    result = {}
    lower_keys = {str(key).lower(): key for key in input_data}
    for field in fields:
        name = field["name"]
        if name in input_data:
            result[name] = input_data[name]
        elif name.lower() in lower_keys:
            result[name] = input_data[lower_keys[name.lower()]]
    return result
def _extract_from_text(
    text: str,
    fields: list[dict[str, Any]],
    reference: date,
    timezone_name: str,
) -> dict[str, Any]:
    result = {}
    email_match = EMAIL_RE.search(text)
    date_value = _extract_date(text, reference)
    time_value = _extract_time(text)
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
        elif field["type"] == "object":
            object_value = _extract_json_object(text, name)
            if object_value is not None:
                result[name] = object_value
        elif "attendee" in lowered:
            emails = EMAIL_RE.findall(text)
            if emails:
                result[name] = emails if field["type"] == "array" else emails[0]
        elif any(word in lowered for word in ("email", "recipient")) and email_match:
            result[name] = email_match.group(0)
        elif _looks_like_date_field(lowered) and date_value:
            if "time" in lowered and time_value:
                result[name] = f"{date_value}T{time_value}:00[{timezone_name}]"
            else:
                result[name] = date_value
        elif any(word in lowered for word in ("title", "subject", "task_name", "event_name")):
            title = _extract_title(text, quoted)
            if title:
                result[name] = title
        elif lowered == "tone":
            tone = _extract_tone(text)
            if tone:
                result[name] = tone
        elif lowered in ("body", "description", "message"):
            result[name] = _replace_relative_dates(text, reference)
        elif lowered == "assigned_to":
            person = _extract_person(text)
            if person:
                result[name] = person
        elif lowered == "table":
            table = re.search(r"\b(?:into|from|table)\s+([A-Za-z_][\w-]*)", text, re.I)
            if table:
                result[name] = table.group(1)
        elif quoted:
            result[name] = quoted[0]
    return result
def _extract_labeled_value(text: str, field_name: str) -> str | None:
    label = re.escape(field_name).replace("_", r"[ _]")
    pattern = rf"\b{label}\s*(?:is|=|:)\s*[\"']?([^,;.\n\"']+)"
    match = re.search(pattern, text, re.I)
    return match.group(1).strip() if match else None
def _extract_enum(text: str, allowed: list[Any] | None) -> Any | None:
    if not allowed:
        return None
    for value in allowed:
        if re.search(rf"\b{re.escape(str(value))}\b", text, re.I):
            return value
    return None
def _extract_date(text: str, reference: date) -> str | None:
    iso = ISO_DATE_RE.search(text)
    if iso:
        return iso.group(1)
    lowered = text.lower()
    if "day after tomorrow" in lowered:
        return (reference + timedelta(days=2)).isoformat()
    if "tomorrow" in lowered:
        return (reference + timedelta(days=1)).isoformat()
    if "today" in lowered:
        return reference.isoformat()
    return None
def _extract_time(text: str) -> str | None:
    match = TIME_RE.search(text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    marker = match.group(3).upper()
    if hour < 1 or hour > 12 or minute > 59:
        return None
    if marker == "AM" and hour == 12:
        hour = 0
    elif marker == "PM" and hour != 12:
        hour += 12
    return f"{hour:02d}:{minute:02d}"
def _extract_title(text: str, quoted: list[str]) -> str | None:
    if quoted:
        return quoted[0]
    match = re.search(
        r"\babout\s+(.+?)(?=\s+(?:today|tomorrow|on\s+\d{4}-\d{2}-\d{2}|at\s+\d)|[.,]|$)",
        text,
        re.I,
    )
    if match:
        title = match.group(1).strip()
        return re.sub(r"^the\s+", "", title, flags=re.I)
    match = re.search(
        r"\b(?:task|event)\s+(?:called|named)\s+(.+?)(?=\s+(?:due|for|on|at)|[.,]|$)",
        text, re.I,
    )
    return match.group(1).strip() if match else None
def _extract_tone(text: str) -> str | None:
    match = re.search(r"\b(?:keep it|tone(?: is|:))\s+([A-Za-z-]+)", text, re.I)
    return match.group(1).lower() if match else None
def _extract_person(text: str) -> str | None:
    match = re.search(r"\b(?:assign(?:ed)? to|owner)\s+([A-Z][A-Za-z'-]+)", text)
    return match.group(1) if match else None
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
def _looks_like_date_field(name: str) -> bool:
    return "date" in name or "time" in name or name in ("start", "end")
def _replace_relative_dates(text: str, reference: date) -> str:
    replacements = {
        "day after tomorrow": (reference + timedelta(days=2)).isoformat(),
        "tomorrow": (reference + timedelta(days=1)).isoformat(),
        "today": reference.isoformat(),
    }
    result = text
    for phrase, value in replacements.items():
        result = re.sub(rf"\b{phrase}\b", value, result, flags=re.I)
    return result
def _normalize_value(
    value: Any,
    field: dict[str, Any],
    reference: date,
    timezone_name: str,
) -> tuple[Any, str | None]:
    target = field["type"]
    try:
        if target == "string":
            normalized = value if isinstance(value, str) else str(value)
            normalized = normalized.strip()
            if field.get("format") == "date":
                relative = _extract_date(normalized, reference)
                normalized = relative or normalized
            if field.get("format") == "email" and not EMAIL_RE.fullmatch(normalized):
                return None, "must be a valid email address"
            return normalized, None
        if target == "integer":
            if isinstance(value, bool):
                raise ValueError
            return int(value), None
        if target == "number":
            if isinstance(value, bool):
                raise ValueError
            return float(value), None
        if target == "boolean":
            if isinstance(value, bool):
                return value, None
            lowered = str(value).strip().lower()
            if lowered in ("true", "yes", "1"):
                return True, None
            if lowered in ("false", "no", "0"):
                return False, None
            raise ValueError
        if target == "object" and isinstance(value, dict):
            return value, None
        if target == "array" and isinstance(value, list):
            return value, None
        if target == "null" and value is None:
            return None, None
    except (TypeError, ValueError):
        pass
    return None, f"could not convert value to {target}"
def _validate(
    payload: dict[str, Any], fields: list[dict[str, Any]]
) -> tuple[list[str], list[dict[str, str]]]:
    missing = []
    issues = []
    for field in fields:
        name = field["name"]
        if name not in payload or payload[name] == "":
            if field["required"]:
                missing.append(name)
            continue
        value = payload[name]
        if not _has_expected_type(value, field["type"]):
            issues.append({"field": name, "message": f"must be {field['type']}"})
        allowed = field.get("enum")
        if allowed and value not in allowed:
            issues.append({"field": name, "message": f"must be one of: {', '.join(map(str, allowed))}"})
        if field.get("format") == "date":
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                issues.append({"field": name, "message": "must use YYYY-MM-DD"})
    return missing, issues
def _has_expected_type(value: Any, expected: str) -> bool:
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "null": lambda item: item is None,
    }
    return checks.get(expected, lambda item: False)(value)
def _python_value_type(value: Any) -> str:
    type_names = {
        bool: "boolean", int: "integer", float: "number",
        dict: "object", list: "array", type(None): "null",
    }
    if type(value) in type_names:
        return type_names[type(value)]
    return "string"
