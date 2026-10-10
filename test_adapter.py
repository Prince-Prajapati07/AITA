import unittest

from adapter import adapt, read_schema


class AdapterTests(unittest.TestCase):
    def test_email_agent_from_text(self):
        schema = {
            "recipient": "string",
            "subject": "string",
            "body": "string",
            "tone": "string",
        }
        result = adapt(
            "Send an email to Rahul at rahul@awd.example.com about the project review "
            "tomorrow at 3 PM. Keep it professional.",
            schema,
            reference_date="2026-10-10",
            timezone="Asia/Kolkata",
        )
        self.assertEqual("ok", result["status"])
        self.assertEqual("rahul@awd.example.com", result["payload"]["recipient"])
        self.assertEqual("project review", result["payload"]["subject"])
        self.assertIn("2026-10-11", result["payload"]["body"])

    def test_database_agent_case_insensitive_dict_keys(self):
        schema = {
            "operation": "insert | update | delete",
            "table": "string",
            "data": {},
            "conditions": {},
        }
        result = adapt(
            {
                "Operation": "update",
                "TABLE": "candidates",
                "data": {"stage": "interview"},
                "conditions": {"email": "rahul@awd.example.com"},
            },
            schema,
        )
        self.assertEqual("ok", result["status"])
        self.assertEqual("update", result["payload"]["operation"])
        self.assertEqual({"stage": "interview"}, result["payload"]["data"])
        self.assertIsInstance(result["payload"]["conditions"], dict)

    def test_task_agent_relative_due_date(self):
        schema = {
            "task_name": "string",
            "assigned_to": "string",
            "priority": "low | medium | high",
            "due_date": "YYYY-MM-DD",
        }
        result = adapt(
            {
                "task_name": "Review application",
                "assigned_to": "Rahul",
                "priority": "high",
                "due_date": "tomorrow",
            },
            schema,
            reference_date="2026-10-10",
        )
        self.assertEqual("2026-10-11", result["payload"]["due_date"])

    def test_missing_required_field_needs_clarification(self):
        schema = {
            "type": "object",
            "properties": {"recipient": {"type": "string", "format": "email"}, "subject": {"type": "string"}},
            "required": ["recipient", "subject"],
        }
        result = adapt("Send an email to rahul@awd.example.com", schema)
        self.assertEqual("needs_clarification", result["status"])
        self.assertIn("subject", result["missing"])
        self.assertIsNone(result["payload"])

    def test_invalid_enum_collects_issue(self):
        schema = {
            "task_name": "string",
            "assigned_to": "string",
            "priority": "low | medium | high",
            "due_date": "YYYY-MM-DD",
        }
        result = adapt(
            {
                "task_name": "Review application",
                "assigned_to": "Rahul",
                "priority": "whenever",
                "due_date": "2026-10-12",
            },
            schema,
        )
        self.assertEqual("needs_clarification", result["status"])
        self.assertTrue(any(issue["field"] == "priority" for issue in result["issues"]))

    def test_schema_reader_marks_optional_fields(self):
        fields = read_schema(
            {
                "type": "object",
                "properties": {"name": {"type": "string"}, "note": {"type": "string"}},
                "required": ["name"],
            }
        )
        self.assertTrue(fields[0]["required"])
        self.assertFalse(fields[1]["required"])


if __name__ == "__main__":
    unittest.main()
