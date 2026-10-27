"""
Solandra Platform Tool Schema
=============================
Consolidates CoreID Admin Console User Management and Solandra Ticketing.
"""

from typing import Dict, Any

SOLANDRA_SCHEMA: Dict[str, Any] = {
    "platform": "solandra",
    "aliases": [
        "coreid",
        "coreid admin console",
        "coreid_user_management",
        "solandra group",
        "solandra corp",
        "solandra_ticketing",
        "solandra_group",
        "ticketing system",
        "ticketing"
    ],
    "description": "Solandra Corp IT Support platform covering CoreID Admin Console user lookup, identity verification, temporary password generation, and ticket resolution.",
    "functions": [
        {
            "function_name": "search_user",
            "description": "Searches the CoreID user directory by employee ID and returns the matching user's account status and profile details.",
            "required_inputs": ["employee_id"],
            "response_schema": {
                "success": {
                    "found": "true",
                    "user_id": "str",
                    "employee_id": "str",
                    "name": "str",
                    "manager_name": "str",
                    "department": "str",
                    "status": "Locked"
                },
                "not_found": {
                    "found": "false",
                    "user_id": "null"
                },
                "error": {
                    "error": "str",
                    "code": "int"
                }
            }
        },
        {
            "function_name": "verify_caller_identity",
            "description": "Verifies the caller against the CoreID identity verification checklist. At least 2 of 4 identity items must match before password reset can proceed.",
            "required_inputs": [
                "user_id",
                "employee_id",
                "manager_name",
                "department",
                "phone_last4"
            ],
            "response_schema": {
                "success": {
                    "verified": "true",
                    "user_id": "str",
                    "matched_items": ["str"],
                    "matched_count": 2,
                    "minimum_required": 2
                },
                "verification_failed": {
                    "verified": "false",
                    "user_id": "str",
                    "matched_items": ["str"],
                    "matched_count": 1,
                    "minimum_required": 2
                },
                "error": {
                    "error": "str",
                    "code": "int"
                }
            }
        },
        {
            "function_name": "generate_temporary_password",
            "description": "Generates a temporary password for a locked user in CoreID Admin Console. Force change at next sign-in must remain enabled.",
            "required_inputs": ["user_id"],
            "response_schema": {
                "success": {
                    "user_id": "str",
                    "status": "success",
                    "temporary_password": "str",
                    "force_change_at_next_sign_in": "true"
                },
                "error": {
                    "error": "str",
                    "code": "int"
                }
            }
        },
        {
            "function_name": "resolve_ticket",
            "description": "Adds the resolution audit note to the password-reset ticket and changes the ticket status to Resolved.",
            "required_inputs": ["ticket_id", "resolution_note"],
            "response_schema": {
                "success": {
                    "ticket_id": "str",
                    "status": "Resolved",
                    "resolution_note": "str",
                    "audit_logged": "true"
                },
                "error": {
                    "error": "str",
                    "code": "int"
                }
            }
        }
    ]
}
