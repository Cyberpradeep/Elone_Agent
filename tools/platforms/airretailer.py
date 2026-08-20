"""
AirRetailer Platform Tool Schema
================================
VPN and Remote Desktop (RDP) tools for Cisco AnyConnect and Microsoft Remote Desktop.
"""

from typing import Dict, Any

AIRRETAILER_SCHEMA: Dict[str, Any] = {
    "platform": "airretailer",
    "aliases": [
        "airretailer",
        "airretailer_vpn_rdp_tools",
        "vpn",
        "rdp",
        "cisco anyconnect"
    ],
    "description": "AirRetailer VPN and Remote Desktop (RDP) tools — VPN portal login, Cisco AnyConnect client installer/settings, VPN connection, and RDP session setup.",
    "functions": [
        {
            "function_name": "derive_vpn_username",
            "description": "Build the VPN username from a person's full name using the company rule (first name + first letter of last name).",
            "required_inputs": ["full_name"],
            "response_schema": {"username": "str"}
        },
        {
            "function_name": "open_vpn_portal",
            "description": "Open the VPN sign-in website in a browser.",
            "required_inputs": [],
            "response_schema": {"page_loaded": True}
        },
        {
            "function_name": "login_vpn_portal",
            "description": "Sign in to the VPN website with a username and password.",
            "required_inputs": ["username", "password"],
            "response_schema": {"session_token": "str", "login_ok": True}
        },
        {
            "function_name": "download_vpn_client",
            "description": "Download the Cisco AnyConnect installer file from the portal after login.",
            "required_inputs": ["os"],
            "response_schema": {"installer_path": "str"}
        },
        {
            "function_name": "install_vpn_client",
            "description": "Run the downloaded installer to install the AnyConnect app on the laptop.",
            "required_inputs": ["installer_path"],
            "response_schema": {"installed": True, "version": "str"}
        },
        {
            "function_name": "launch_vpn_client",
            "description": "Open the installed Cisco AnyConnect app.",
            "required_inputs": [],
            "response_schema": {"app_open": True}
        },
        {
            "function_name": "open_vpn_client_settings",
            "description": "Open the settings (gear icon) panel inside the AnyConnect app.",
            "required_inputs": [],
            "response_schema": {"settings_open": True}
        },
        {
            "function_name": "apply_vpn_client_settings",
            "description": "Turn the AnyConnect preference checkboxes on or off to match the SOP settings.",
            "required_inputs": ["preferences"],
            "response_schema": {"applied": True}
        },
        {
            "function_name": "set_vpn_server_address",
            "description": "Type the VPN server address into AnyConnect so it knows where to connect.",
            "required_inputs": ["server_url"],
            "response_schema": {"saved": True}
        },
        {
            "function_name": "connect_vpn",
            "description": "Start the VPN connection. Can auto-accept the security warning ('Connect Anyway').",
            "required_inputs": ["username", "password"],
            "response_schema": {"connected": True, "assigned_ip": "str"}
        },
        {
            "function_name": "check_vpn_status",
            "description": "Check whether the VPN is currently connected.",
            "required_inputs": [],
            "response_schema": {"connected": True, "duration_seconds": 120}
        },
        {
            "function_name": "get_office_pc_ip",
            "description": "Look up the office PC's local network address (the IP address the remote desktop app needs).",
            "required_inputs": [],
            "response_schema": {"ip_address": "str"}
        },
        {
            "function_name": "get_office_pc_username",
            "description": "Look up the login username used on the office PC for remote desktop connection.",
            "required_inputs": [],
            "response_schema": {"username": "str", "domain": "str"}
        },
        {
            "function_name": "format_remote_login",
            "description": "Format the remote desktop username according to the operating system domain conventions.",
            "required_inputs": ["username", "os"],
            "response_schema": {"formatted_username": "str"}
        },
        {
            "function_name": "install_remote_desktop_app",
            "description": "Install the Microsoft Remote Desktop application on the user's computer.",
            "required_inputs": ["os"],
            "response_schema": {"installed": True}
        },
        {
            "function_name": "launch_remote_desktop_app",
            "description": "Open the Microsoft Remote Desktop application on the user's computer.",
            "required_inputs": [],
            "response_schema": {"app_open": True}
        },
        {
            "function_name": "add_remote_pc",
            "description": "Save the office PC configuration in the remote desktop app using its network IP address.",
            "required_inputs": ["ip_address"],
            "response_schema": {"pc_id": "str"}
        },
        {
            "function_name": "connect_remote_pc",
            "description": "Start the remote desktop session using the saved PC configuration and credentials.",
            "required_inputs": ["pc_id", "formatted_username", "password"],
            "response_schema": {"session_active": True, "session_id": "str"}
        },
        {
            "function_name": "disconnect_remote_pc",
            "description": "End the active remote desktop session.",
            "required_inputs": ["session_id"],
            "response_schema": {"closed": True}
        },
        {
            "function_name": "disconnect_vpn",
            "description": "Disconnect and turn off the active VPN connection.",
            "required_inputs": [],
            "response_schema": {"disconnected": True}
        }
    ]
}
