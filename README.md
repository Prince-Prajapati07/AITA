# Adaptive Input Transformation Agent

This small Python project converts a dictionary or free text into JSON for a receiving agent. The adapter reads the receiving agent's schema at runtime, extracts available values, normalizes their types, and validates the complete result. There are no agent-specific transformation functions.

The safety boundary is deliberate: this project only builds payloads. It never sends email, changes a database, creates a task, calls an external service, or performs any other consequential action.

## Data flow

```text
dict or free text + target schema + date context
                    |
                    v
read fields -> extract values -> normalize values -> validate all fields
                                                       |
                                                       v
                          ok + payload, or needs_clarification + details
```

`adapt(input_data, schema, reference_date=None, timezone="UTC")` is the only public transformation entry point. It accepts standard JSON Schema objects and the compact schema notation used in the assignment. In compact schemas, every listed field is considered required. With standard JSON Schema, the `required` array controls this.

Relative dates use the caller's `reference_date` and IANA timezone. If no date is supplied, the adapter uses today's date in the supplied timezone (UTC by default). This behavior is explicit in the API rather than inferred from the input.

## Run

Python 3.11 or newer is recommended because the standard-library timezone database interface is used.

```bash
python demo.py
python -m unittest
```

The demo runs Email, Database, and Task Management contracts, followed by a new Calendar contract. All four call the same unchanged `adapt()` function.

## Assumptions and limitations

- Dictionary keys are matched exactly first, then case-insensitively. Unknown keys are ignored.
- Text extraction deliberately uses small regexes and naming conventions. It recognizes common emails, ISO and relative dates, 12-hour times, quoted titles, labeled values, and a few ordinary phrases. It will not reliably understand pronouns, unusual sentence structure, ambiguous dates, misspellings, or complex nested objects.
- Relative dates are limited to `today`, `tomorrow`, and `day after tomorrow`. Timezone conversion between zones is not attempted.
- This is a useful deterministic baseline, not a full implementation of the JSON Schema specification.
- An LLM extractor could later replace `_extract_from_text` while leaving normalization and validation in place. Its output must still pass type/schema validation, enum checks, and required-field checks. Critical values such as names, email addresses, and dates must also be traceable to exact evidence in the input text; otherwise they must be reported as missing rather than invented.
