"""
Dummy / Standalone Tool Catalog for SOP Ingestion Pipeline Testing
===================================================================
Mirrors the exact same structure as the main app's shared/tool_catalog.py
but uses hardcoded metadata dicts instead of importing live provider classes.

This lets the JIT Converter's 4-Gate tool-matching logic run without
needing the actual Auth0, MockProvider, or SystemOps dependencies.

When you integrate back into the main app, replace this with:
    from shared.tool_catalog import TOOL_CATALOG, PROVIDER_NAMES, ...
"""

# ---------------------------------------------------------------------------
# Static tool catalog metadata (same shape as BaseProvider.get_tool_metadata)
# ---------------------------------------------------------------------------

TOOL_CATALOG = [
    # --- System Operations Provider ---
    {
        "tool_name": "system_operations",
        "platform": "system",
        "description": "System operation tools including email notifications.",
        "functions": [
            {
                "function_name": "send_email",
                "description": "Sends an email to the user with ticket updates, instructions, or resolution tokens.",
                "required_inputs": ["to_email", "subject", "body"],
                "response_schema": {
                    "success": {"status": "ok", "message": "str"},
                    "error": {"status": "error", "message": "str"},
                },
            }
        ],
    },
    # --- Auth0 Provider ---
    {
        "tool_name": "auth0_user_management",
        "platform": "auth0",
        "description": "Auth0 User Identity Management tools for searching users, triggering password resets, and unlocking accounts.",
        "functions": [
            {
                "function_name": "search_user",
                "description": "Search Auth0 user profile by email.",
                "required_inputs": ["email"],
                "response_schema": {
                    "success": {"found": "bool", "user_id": "str", "details": {"email": "str", "name": "str", "blocked": "bool"}},
                    "not_found": {"found": False, "user_id": None},
                    "error": {"error": "str", "code": "int"},
                },
            },
            {
                "function_name": "trigger_password_reset",
                "description": "Sends Auth0 password reset email.",
                "required_inputs": ["email"],
                "response_schema": {
                    "success": {"status": "success", "email_sent": "bool", "message": "str"},
                    "error": {"error": "str", "code": "int"},
                },
            },
            {
                "function_name": "unlock_user_account",
                "description": "Unlocks a locked Auth0 user account by user_id.",
                "required_inputs": ["user_id"],
                "response_schema": {
                    "success": {"status": "unlocked", "user_id": "str"},
                    "error": {"status": "failed", "user_id": "str"},
                },
            },
        ],
    },
    # --- Mock Support Platform (L1 Testing) ---
    {
        "tool_name": "l1_testing_platform_api",
        "platform": "mock",
        "description": "REST API client for L1 Support Platform — covers auth, password management, MFA, admin user management, and audit logging.",
        "functions": [
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
                "description": "POST /api/auth/login — Login with email and password.",
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
    },
    # --- AirRetailer VPN + Remote Desktop Tool Catalog ---
    {
        "tool_name": "airretailer_vpn_rdp_tools",
        "platform": "airretailer",
        "description": "AirRetailer VPN + Remote Desktop — Tool Catalog for VPN setup, Cisco AnyConnect client management, and RDP remote desktop connection.",
        "functions": [
            {
                "function_name": "derive_vpn_username",
                "description": "Build the VPN username from a person's full name using the company rule (first name + first letter of last name).",
                "required_inputs": ["full_name"],
                "response_schema": {"username": "str"},
            },
            {
                "function_name": "open_vpn_portal",
                "description": "Open the VPN sign-in website in a browser.",
                "required_inputs": [],
                "response_schema": {"page_loaded": True},
            },
            {
                "function_name": "login_vpn_portal",
                "description": "Sign in to the VPN website with a username and password.",
                "required_inputs": ["username", "password"],
                "response_schema": {"session_token": "str", "login_ok": True},
            },
            {
                "function_name": "download_vpn_client",
                "description": "Download the Cisco AnyConnect installer file from the portal after login.",
                "required_inputs": ["os"],
                "response_schema": {"installer_path": "str"},
            },
            {
                "function_name": "install_vpn_client",
                "description": "Run the downloaded installer to install the AnyConnect app on the laptop.",
                "required_inputs": ["installer_path"],
                "response_schema": {"installed": True, "version": "str"},
            },
            {
                "function_name": "launch_vpn_client",
                "description": "Open the installed Cisco AnyConnect app.",
                "required_inputs": [],
                "response_schema": {"app_open": True},
            },
            {
                "function_name": "open_vpn_client_settings",
                "description": "Open the settings (gear icon) panel inside the AnyConnect app.",
                "required_inputs": [],
                "response_schema": {"settings_open": True},
            },
            {
                "function_name": "apply_vpn_client_settings",
                "description": "Turn the AnyConnect preference checkboxes on or off to match the SOP screenshot.",
                "required_inputs": ["preferences"],
                "response_schema": {"applied": True},
            },
            {
                "function_name": "set_vpn_server_address",
                "description": "Type the VPN server address into AnyConnect so it knows where to connect.",
                "required_inputs": ["server_url"],
                "response_schema": {"saved": True},
            },
            {
                "function_name": "connect_vpn",
                "description": "Start the VPN connection. Can auto-accept the security warning ('Connect Anyway').",
                "required_inputs": ["username", "password"],
                "response_schema": {"connected": True, "assigned_ip": "str"},
            },
            {
                "function_name": "check_vpn_status",
                "description": "Check whether the VPN is currently connected.",
                "required_inputs": [],
                "response_schema": {"connected": True, "duration_seconds": 120},
            },
            {
                "function_name": "get_office_pc_ip",
                "description": "Look up the office PC's local network address (the number the remote desktop app needs to find it).",
                "required_inputs": [],
                "response_schema": {"ip_address": "str"},
            },
            {
                "function_name": "get_office_pc_username",
                "description": "Look up the login name used on the office PC, so it can be typed into the remote desktop app.",
                "required_inputs": [],
                "response_schema": {"username": "str", "domain": "str"},
            },
            {
                "function_name": "format_remote_login",
                "description": "Put the username into the correct shape for the operating system being used.",
                "required_inputs": ["username", "os"],
                "response_schema": {"formatted_username": "str"},
            },
            {
                "function_name": "install_remote_desktop_app",
                "description": "Install the Microsoft Remote Desktop app (mainly needed on Mac).",
                "required_inputs": ["os"],
                "response_schema": {"installed": True},
            },
            {
                "function_name": "launch_remote_desktop_app",
                "description": "Open the Microsoft Remote Desktop app on the personal laptop.",
                "required_inputs": [],
                "response_schema": {"app_open": True},
            },
            {
                "function_name": "add_remote_pc",
                "description": "Save the office PC in the remote desktop app by entering its network address.",
                "required_inputs": ["ip_address"],
                "response_schema": {"pc_id": "str"},
            },
            {
                "function_name": "connect_remote_pc",
                "description": "Start the remote desktop session using the saved PC and the login details.",
                "required_inputs": ["pc_id", "formatted_username", "password"],
                "response_schema": {"session_active": True, "session_id": "str"},
            },
            {
                "function_name": "disconnect_remote_pc",
                "description": "End the remote desktop session.",
                "required_inputs": ["session_id"],
                "response_schema": {"closed": True},
            },
            {
                "function_name": "disconnect_vpn",
                "description": "Turn off the VPN connection.",
                "required_inputs": [],
                "response_schema": {"disconnected": True},
            },
        ],
    },
]

# Derived constants (mirror the main app's tool_catalog.py helpers)
PROVIDER_NAMES = list({tool["tool_name"] for tool in TOOL_CATALOG} | {"system", "auth0", "mock_support_platform", "airretailer"})


def get_tool_names(catalog: list) -> set:
    return {tool["tool_name"] for tool in catalog}


def get_function_names(catalog: list, tool_name: str) -> set:
    funcs = set()
    for tool in catalog:
        if tool.get("tool_name") == tool_name or tool_name in str(tool):
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    if not funcs:
        for tool in catalog:
            for f in tool.get("functions", []):
                funcs.add(f["function_name"])
    return funcs


def get_required_inputs(catalog: list, tool_name: str, function_name: str):
    for tool in catalog:
        if tool.get("tool_name") == tool_name or tool_name in str(tool):
            for f in tool.get("functions", []):
                if f["function_name"] == function_name:
                    return f.get("required_inputs", [])
    # Global function search fallback
    for tool in catalog:
        for f in tool.get("functions", []):
            if f["function_name"] == function_name:
                return f.get("required_inputs", [])
    return None


def get_formatted_tools_summary() -> str:
    """Returns a comprehensive, human-readable summary of all registered tool platforms from tools.platforms."""
    import json
    try:
        from tools.platforms import DETAILED_TOOL_SCHEMAS
        summary_lines = []
        for plat_key, schema in sorted(DETAILED_TOOL_SCHEMAS.items()):
            platform = schema.get("platform", plat_key)
            desc = schema.get("description", "No description provided.")
            aliases = schema.get("aliases", [])
            alias_str = f" (Aliases: {', '.join(aliases)})" if aliases else ""
            summary_lines.append(f"- Platform: '{platform}'{alias_str}")
            summary_lines.append(f"  Description: {desc}")
            summary_lines.append("  Available Functions:")
            for fn in schema.get("functions", []):
                req_inputs = ", ".join(fn.get("required_inputs", []))
                fn_desc = fn.get("description", "")
                fn_name = fn.get("function_name", "")
                summary_lines.append(f"    * {fn_name}({req_inputs}): {fn_desc}")
                resp_schema = fn.get("response_schema")
                if resp_schema:
                    summary_lines.append(f"      → Response Schema: {json.dumps(resp_schema)}")
        return "\n".join(summary_lines)
    except Exception:
        summary_lines = []
        for tool in TOOL_CATALOG:
            tool_name = tool.get("tool_name", "unknown")
            platform = tool.get("platform", "generic")
            desc = tool.get("description", "No description provided.")
            summary_lines.append(f"- Tool Name: '{tool_name}' (Platform: '{platform}')")
            summary_lines.append(f"  Description: {desc}")
            summary_lines.append("  Available Functions:")
            for fn in tool.get("functions", []):
                req_inputs = ", ".join(fn.get("required_inputs", []))
                fn_desc = fn.get("description", "")
                summary_lines.append(f"    * {fn['function_name']}({req_inputs}): {fn_desc}")
                resp_schema = fn.get("response_schema") or fn.get("returns")
                if resp_schema:
                    summary_lines.append(f"      → Response Schema: {json.dumps(resp_schema)}")
        return "\n".join(summary_lines)
