"""
Email Platform Tool Schema
==========================
Communication service for sending notification emails.
"""

from typing import Dict, Any

EMAIL_SCHEMA: Dict[str, Any] = {
    "platform": "email",
    "aliases": [
        "email",
        "email_service",
        "communication",
        "mail",
        "notification"
    ],
    "description": "Email service for sending ticket updates, instructions, or resolution notifications to users.",
    "functions": [
        {
            "function_name": "send_email",
            "description": "Sends an email to the user with ticket updates, instructions, or resolution tokens.",
            "required_inputs": ["to_email", "subject", "body"],
            "response_schema": {
                "success": {"status": "ok", "message": "str"},
                "error": {"status": "error", "message": "str"}
            }
        }
    ]
}
