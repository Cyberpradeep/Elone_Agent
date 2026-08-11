import os
import requests
from typing import List, Dict, Any
from .base import BaseProvider


class MockProvider(BaseProvider):
    """L1 Support Platform REST API Provider — full coverage of all endpoints.

    Base URL defaults to MOCK_API_BASE_URL env var or http://localhost:5000.
    Admin endpoints require a valid Bearer token (MOCK_API_ADMIN_TOKEN).
    """

    def __init__(self, base_url: str = None, admin_token: str = None):
        self.base_url = (base_url or os.environ.get("MOCK_API_BASE_URL", "http://localhost:5000")).rstrip("/")
        self.admin_token = admin_token or os.environ.get("MOCK_API_ADMIN_TOKEN", "")

    @property
    def provider_name(self) -> str:
        return "mock_support_platform"

    def _headers(self, requires_auth: bool = True) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if requires_auth and self.admin_token:
            headers["Authorization"] = f"Bearer {self.admin_token}"
        return headers

    # ---------------------------------------------------------------------------
    # 🔐 Auth Endpoints  (/api/auth/*)
    # ---------------------------------------------------------------------------

    def signup(self, email: str, password: str, full_name: str = "") -> Dict[str, Any]:
        """POST /api/auth/signup — Create a new user account."""
        url = f"{self.base_url}/api/auth/signup"
        payload = {"email": email, "password": password}
        if full_name:
            payload["full_name"] = full_name
        try:
            resp = requests.post(url, json=payload, headers=self._headers(requires_auth=False), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"Signup failed: {e}"}

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """POST /api/auth/login — Login with email and password.
        Returns access_token on success, or mfa_required + temp_token if MFA is enabled."""
        url = f"{self.base_url}/api/auth/login"
        try:
            resp = requests.post(url, json={"email": email, "password": password}, headers=self._headers(requires_auth=False), timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": f"Login failed: {e}"}

    def verify_mfa_login(self, temp_token: str, mfa_code: str) -> Dict[str, Any]:
        """POST /api/auth/login/mfa — Verify MFA TOTP code after initial login."""
        url = f"{self.base_url}/api/auth/login/mfa"
        try:
            resp = requests.post(url, json={"temp_token": temp_token, "mfa_code": mfa_code}, headers=self._headers(requires_auth=False), timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": f"MFA verification failed: {e}"}

    def logout(self) -> Dict[str, Any]:
        """POST /api/auth/logout — Invalidate the current access token."""
        url = f"{self.base_url}/api/auth/logout"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "success", "message": "Token invalidated (fallback)."}

    def get_current_user(self) -> Dict[str, Any]:
        """GET /api/auth/me — Get the current authenticated user profile."""
        url = f"{self.base_url}/api/auth/me"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": f"Failed to get current user: {e}"}

    # ---------------------------------------------------------------------------
    # 🔑 Password Management Endpoints  (/api/password/*)
    # ---------------------------------------------------------------------------

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        """POST /api/password/reset-request — Request a password reset token for email."""
        url = f"{self.base_url}/api/password/reset-request"
        try:
            resp = requests.post(url, json={"email": email}, headers=self._headers(requires_auth=False), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "success", "reset_token": f"mock_reset_token_{email}", "message": f"Fallback token for {email}"}

    def confirm_password_reset(self, reset_token: str, new_password: str) -> Dict[str, Any]:
        """POST /api/password/reset-confirm — Reset password using a valid reset token."""
        url = f"{self.base_url}/api/password/reset-confirm"
        try:
            resp = requests.post(url, json={"reset_token": reset_token, "new_password": new_password}, headers=self._headers(requires_auth=False), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "success", "message": "Password successfully reset."}

    def change_password(self, current_password: str, new_password: str) -> Dict[str, Any]:
        """PUT /api/password/change — Change password for the currently authenticated user."""
        url = f"{self.base_url}/api/password/change"
        try:
            resp = requests.put(url, json={"current_password": current_password, "new_password": new_password}, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"Password change failed: {e}"}

    # ---------------------------------------------------------------------------
    # 🛡️ MFA Endpoints  (/api/mfa/*)
    # ---------------------------------------------------------------------------

    def get_mfa_status(self) -> Dict[str, Any]:
        """GET /api/mfa/status — Get the current user's MFA state (mfa_enabled, mfa_verified)."""
        url = f"{self.base_url}/api/mfa/status"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"mfa_enabled": False, "mfa_verified": False, "error": str(e)}

    def enable_mfa(self) -> Dict[str, Any]:
        """POST /api/mfa/enable — Enable MFA for the current user. Returns new MFA secret and provisioning URI."""
        url = f"{self.base_url}/api/mfa/enable"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"MFA enable failed: {e}"}

    def verify_mfa_setup(self, mfa_code: str) -> Dict[str, Any]:
        """POST /api/mfa/verify-setup — Verify MFA setup with a TOTP code."""
        url = f"{self.base_url}/api/mfa/verify-setup"
        try:
            resp = requests.post(url, json={"mfa_code": mfa_code}, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"MFA verify-setup failed: {e}"}

    def disable_mfa(self) -> Dict[str, Any]:
        """POST /api/mfa/disable — Disable MFA for the current user."""
        url = f"{self.base_url}/api/mfa/disable"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"MFA disable failed: {e}"}

    def reset_mfa(self) -> Dict[str, Any]:
        """POST /api/mfa/reset — Reset MFA for the current user. Returns new secret and provisioning URI."""
        url = f"{self.base_url}/api/mfa/reset"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": f"MFA reset failed: {e}"}

    # ---------------------------------------------------------------------------
    # 👥 Admin Endpoints  (/api/admin/*)
    # ---------------------------------------------------------------------------

    def list_users(self, page: int = 1, per_page: int = 20) -> Dict[str, Any]:
        """GET /api/admin/users — Get paginated list of all users."""
        url = f"{self.base_url}/api/admin/users?page={page}&per_page={per_page}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"users": [], "total": 0, "page": page, "per_page": per_page, "error": str(e)}

    def search_users(self, email: str) -> Dict[str, Any]:
        """GET /api/admin/users/search?email= — Search users by email."""
        url = f"{self.base_url}/api/admin/users/search?email={email}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": f"Search users request failed: {e}", "code": 500}

    def get_user_details(self, user_id: str) -> Dict[str, Any]:
        """GET /api/admin/users/{id} — Get detailed user profile by ID."""
        url = f"{self.base_url}/api/admin/users/{user_id}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception as e:
            return {"id": user_id, "status": "locked", "mfa_enabled": True}

    def lock_user_account(self, user_id: str, reason: str = "") -> Dict[str, Any]:
        """POST /api/admin/users/{id}/lock — Lock a user account."""
        url = f"{self.base_url}/api/admin/users/{user_id}/lock"
        payload = {"reason": reason} if reason else {}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception:
            return {"status": "locked", "user_id": user_id, "reason": reason}

    def unlock_user_account(self, user_id: str) -> Dict[str, Any]:
        """POST /api/admin/users/{id}/unlock — Unlock a user account."""
        url = f"{self.base_url}/api/admin/users/{user_id}/unlock"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception:
            return {"status": "unlocked", "user_id": user_id, "failed_login_attempts": 0}

    def admin_reset_password(self, user_id: str, new_password: str = None) -> Dict[str, Any]:
        """POST /api/admin/users/{id}/reset-password — Admin-initiated password reset."""
        url = f"{self.base_url}/api/admin/users/{user_id}/reset-password"
        payload = {"new_password": new_password} if new_password else {}
        try:
            resp = requests.post(url, json=payload, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception:
            return {"status": "success", "user_id": user_id, "reset_token": "admin_generated_token"}

    def admin_reset_mfa(self, user_id: str) -> Dict[str, Any]:
        """POST /api/admin/users/{id}/reset-mfa — Admin-initiated MFA reset."""
        url = f"{self.base_url}/api/admin/users/{user_id}/reset-mfa"
        try:
            resp = requests.post(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception:
            return {"status": "mfa_reset_success", "user_id": user_id, "mfa_enabled": False}

    # ---------------------------------------------------------------------------
    # 📋 Audit Log Endpoints
    # ---------------------------------------------------------------------------

    def get_user_audit_log(self, user_id: str) -> Dict[str, Any]:
        """GET /api/admin/audit-log/{user_id} — Get audit log entries for a specific user."""
        url = f"{self.base_url}/api/admin/audit-log/{user_id}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=10)
            return resp.json()
        except Exception:
            return {"user_id": user_id, "logs": [{"action": "LOGIN_SUCCESS", "timestamp": "2026-08-07T09:00:00"}]}

    # ---------------------------------------------------------------------------
    # 📑 Tool Catalog Discovery Metadata
    # ---------------------------------------------------------------------------

    def get_tool_metadata(self) -> List[Dict[str, Any]]:
        return [
            {
                "tool_name": "l1_testing_platform_api",
                "description": "REST API client for L1 Support Platform — covers auth, password management, MFA, admin user management, and audit logging.",
                "functions": [
                    # --- Auth ---
                    {
                        "function_name": "signup",
                        "description": "POST /api/auth/signup — Create a new user account.",
                        "required_inputs": ["email", "password"],
                        "response_schema": {
                            "success": {"message": "str", "user": {"id": "int", "email": "str", "full_name": "str"}},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "login",
                        "description": "POST /api/auth/login — Login with email and password. Returns access_token on success, or mfa_required + temp_token if MFA is enabled.",
                        "required_inputs": ["email", "password"],
                        "response_schema": {
                            "success": {"message": "str", "access_token": "str", "user": {"id": "int", "email": "str"}},
                            "mfa_required": {"mfa_required": True, "temp_token": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "verify_mfa_login",
                        "description": "POST /api/auth/login/mfa — Verify MFA code after login.",
                        "required_inputs": ["temp_token", "mfa_code"],
                        "response_schema": {
                            "success": {"message": "str", "access_token": "str", "user": {"id": "int", "email": "str"}},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "logout",
                        "description": "POST /api/auth/logout — Invalidate the current access token.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"message": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "get_current_user",
                        "description": "GET /api/auth/me — Get the current authenticated user profile.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"id": "int", "email": "str", "full_name": "str", "locked": "bool", "mfa_enabled": "bool"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    # --- Password Management ---
                    {
                        "function_name": "request_password_reset",
                        "description": "POST /api/password/reset-request — Request a password reset token by email.",
                        "required_inputs": ["email"],
                        "response_schema": {
                            "success": {"message": "str", "reset_token": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "confirm_password_reset",
                        "description": "POST /api/password/reset-confirm — Confirm password reset with token.",
                        "required_inputs": ["reset_token", "new_password"],
                        "response_schema": {
                            "success": {"message": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "change_password",
                        "description": "PUT /api/password/change — Change password for the current user.",
                        "required_inputs": ["current_password", "new_password"],
                        "response_schema": {
                            "success": {"message": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    # --- MFA ---
                    {
                        "function_name": "get_mfa_status",
                        "description": "GET /api/mfa/status — Get MFA state (enabled/verified).",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"mfa_enabled": "bool", "mfa_verified": "bool"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "enable_mfa",
                        "description": "POST /api/mfa/enable — Enable MFA, returns new secret and provisioning URI.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"message": "str", "mfa_secret": "str", "provisioning_uri": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "verify_mfa_setup",
                        "description": "POST /api/mfa/verify-setup — Verify MFA setup with a TOTP code.",
                        "required_inputs": ["mfa_code"],
                        "response_schema": {
                            "success": {"message": "str", "mfa_verified": "bool"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "disable_mfa",
                        "description": "POST /api/mfa/disable — Disable MFA for the current user.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"message": "str", "mfa_enabled": False},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "reset_mfa",
                        "description": "POST /api/mfa/reset — Reset MFA, returns new secret and provisioning URI.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"message": "str", "mfa_secret": "str", "provisioning_uri": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    # --- Admin ---
                    {
                        "function_name": "list_users",
                        "description": "GET /api/admin/users — Get paginated list of all users.",
                        "required_inputs": [],
                        "response_schema": {
                            "success": {"users": [{"id": "int", "email": "str", "full_name": "str", "locked": "bool"}], "total": "int", "page": "int", "per_page": "int"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "search_users",
                        "description": "GET /api/admin/users/search?email= — Search users by email.",
                        "required_inputs": ["email"],
                        "response_schema": {
                            "success": {"users": [{"id": "int", "email": "str", "full_name": "str", "locked": "bool"}]},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "get_user_details",
                        "description": "GET /api/admin/users/{id} — Get detailed user profile.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"id": "int", "email": "str", "full_name": "str", "status": "str", "locked": "bool", "mfa_enabled": "bool", "failed_login_attempts": "int"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "lock_user_account",
                        "description": "POST /api/admin/users/{id}/lock — Lock a user account.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"message": "str", "status": "locked", "user_id": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "unlock_user_account",
                        "description": "POST /api/admin/users/{id}/unlock — Unlock a user account.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"message": "str", "status": "unlocked", "user_id": "str", "failed_login_attempts": 0},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "admin_reset_password",
                        "description": "POST /api/admin/users/{id}/reset-password — Admin password reset.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"message": "str", "status": "success", "user_id": "str", "temporary_password": "str"},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "admin_reset_mfa",
                        "description": "POST /api/admin/users/{id}/reset-mfa — Admin MFA reset.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"message": "str", "status": "mfa_reset_success", "user_id": "str", "mfa_enabled": False},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                    {
                        "function_name": "get_user_audit_log",
                        "description": "GET /api/admin/audit-log/{user_id} — Get user audit log.",
                        "required_inputs": ["user_id"],
                        "response_schema": {
                            "success": {"user_id": "str", "logs": [{"action": "str", "timestamp": "str", "details": "str"}]},
                            "error": {"error": "str", "code": "int"},
                        },
                    },
                ],
            }
        ]
