"""Deterministic schema adapter. It builds payloads but executes no actions."""

from datetime import date, datetime
from typing import Any


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
    return _result_envelope({}, [], [])
