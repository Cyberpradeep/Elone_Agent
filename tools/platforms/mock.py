"""
Mock Platform Tool Schema (COMMENTED OUT)
=========================================
L1 Support Platform REST API client covering auth, password management, MFA, and admin operations.
"""

from typing import Dict, Any

# MOCK_SCHEMA: Dict[str, Any] = {
#     "platform": "mock",
#     "aliases": [
#         "mock",
#         "l1_testing_platform_api",
#         "mock_support_platform"
#     ],
#     "description": "L1 Support Platform test API client covering user authentication, password management, MFA setup/verification, account lock/unlock, and audit logging.",
#     "functions": [
#         {
#             "function_name": "signup",
#             "description": "Create a new user account with email and password.",
#             "required_inputs": ["email", "password"],
#             "response_schema": {
#                 "success": {"message": "str", "user": {"id": "int", "email": "str", "full_name": "str"}},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "login",
#             "description": "Log in with email and password.",
#             "required_inputs": ["email", "password"],
#             "response_schema": {
#                 "success": {"message": "str", "access_token": "str", "user": {"id": "int", "email": "str"}},
#                 "mfa_required": {"mfa_required": True, "temp_token": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "verify_mfa_login",
#             "description": "Verify MFA code after login to complete authentication.",
#             "required_inputs": ["temp_token", "mfa_code"],
#             "response_schema": {
#                 "success": {"message": "str", "access_token": "str", "user": {"id": "int", "email": "str"}},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "logout",
#             "description": "Invalidate the current user access token.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"message": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "get_current_user",
#             "description": "Get profile details and lock/MFA status of the currently authenticated user.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"id": "int", "email": "str", "full_name": "str", "locked": "bool", "mfa_enabled": "bool"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "request_password_reset",
#             "description": "Request a password reset token by email.",
#             "required_inputs": ["email"],
#             "response_schema": {
#                 "success": {"message": "str", "reset_token": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "confirm_password_reset",
#             "description": "Confirm password reset using a reset token and new password.",
#             "required_inputs": ["reset_token", "new_password"],
#             "response_schema": {
#                 "success": {"message": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "change_password",
#             "description": "Change the password for the currently authenticated user.",
#             "required_inputs": ["current_password", "new_password"],
#             "response_schema": {
#                 "success": {"message": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "get_mfa_status",
#             "description": "Get current MFA state (enabled/verified).",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"mfa_enabled": "bool", "mfa_verified": "bool"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "enable_mfa",
#             "description": "Enable MFA and generate new secret and provisioning URI.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"message": "str", "mfa_secret": "str", "provisioning_uri": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "verify_mfa_setup",
#             "description": "Verify MFA setup with a TOTP verification code.",
#             "required_inputs": ["mfa_code"],
#             "response_schema": {
#                 "success": {"message": "str", "mfa_verified": "bool"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "disable_mfa",
#             "description": "Disable MFA for the current user.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"message": "str", "mfa_enabled": False},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "reset_mfa",
#             "description": "Reset MFA and generate a new secret and provisioning URI.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"message": "str", "mfa_secret": "str", "provisioning_uri": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "list_users",
#             "description": "Get a paginated list of all registered users.",
#             "required_inputs": [],
#             "response_schema": {
#                 "success": {"users": [{"id": "int", "email": "str", "full_name": "str", "locked": "bool"}], "total": "int", "page": "int", "per_page": "int"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "search_users",
#             "description": "Search users in the directory by email address.",
#             "required_inputs": ["email"],
#             "response_schema": {
#                 "success": {"users": [{"id": "int", "email": "str", "full_name": "str", "locked": "bool"}]},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "get_user_details",
#             "description": "Get detailed user profile including lock status, MFA status, and failed login count.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"id": "int", "email": "str", "full_name": "str", "status": "str", "locked": "bool", "mfa_enabled": "bool", "failed_login_attempts": "int"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "lock_user_account",
#             "description": "Lock a user account by user ID.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"message": "str", "status": "locked", "user_id": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "unlock_user_account",
#             "description": "Unlock a locked user account by user ID.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"message": "str", "status": "unlocked", "user_id": "str", "failed_login_attempts": 0},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "admin_reset_password",
#             "description": "Admin reset password for a specified user ID.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"message": "str", "status": "success", "user_id": "str", "temporary_password": "str"},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "admin_reset_mfa",
#             "description": "Admin reset MFA for a specified user ID.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"message": "str", "status": "mfa_reset_success", "user_id": "str", "mfa_enabled": False},
#                 "error": {"error": "str", "code": "int"}
#             }
#         },
#         {
#             "function_name": "get_user_audit_log",
#             "description": "Get audit logs for a specific user ID.",
#             "required_inputs": ["user_id"],
#             "response_schema": {
#                 "success": {"user_id": "str", "logs": [{"action": "str", "timestamp": "str", "details": "str"}]},
#                 "error": {"error": "str", "code": "int"}
#             }
#         }
#     ]
# }

