import json

from adapter import adapt


REFERENCE_DATE = "2026-10-10"


def show(name, input_data, schema):
    print(f"\n{name}")
    print(json.dumps(adapt(input_data, schema, REFERENCE_DATE, "Asia/Kolkata"), indent=2))


email_schema = {
    "recipient": "string",
    "subject": "string",
    "body": "string",
    "tone": "string",
}

database_schema = {
    "operation": "insert | update | delete",
    "table": "string",
    "data": {},
    "conditions": {},
}

task_schema = {
    "task_name": "string",
    "assigned_to": "string",
    "priority": "low | medium | high",
    "due_date": "YYYY-MM-DD",
}

# A new contract: adapter.py does not know that a Calendar Agent exists.
calendar_schema = {
    "type": "object",
    "properties": {
        "event_title": {"type": "string"},
        "start_time": {"type": "string"},
        "attendees": {"type": "array"},
    },
    "required": ["event_title", "start_time", "attendees"],
}


if __name__ == "__main__":
    show(
        "Email Agent",
        "Send an email to Rahul at rahul@awd.example.com about the project review "
        "tomorrow at 3 PM. Keep it professional.",
        email_schema,
    )
    show(
        "Database Agent",
        {
            "Operation": "insert",
            "TABLE": "applications",
            "data": {"email": "rahul@awd.example.com", "stage": "screening"},
            "conditions": {},
        },
        database_schema,
    )
    show(
        "Task Management Agent",
        {
            "task_name": "Review internship submission",
            "assigned_to": "Rahul",
            "priority": "high",
            "due_date": "tomorrow",
        },
        task_schema,
    )
    show(
        "Calendar Agent (new schema, unchanged adapter)",
        'Create an event called "Project review" tomorrow at 3 PM with '
        "rahul@awd.example.com and anita@awd.example.com.",
        calendar_schema,
    )
