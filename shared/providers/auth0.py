import os
import json
import requests
from typing import List, Dict, Any
from .base import BaseProvider


class Auth0Provider(BaseProvider):
    """Auth0 Management API Tool Provider for Identity & Access Operations."""

    def __init__(self, domain: str = None, client_id: str = None, client_secret: str = None):
        self.domain = domain or os.environ.get("AUTH0_DOMAIN", "")
        self.client_id = client_id or os.environ.get("AUTH0_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("AUTH0_CLIENT_SECRET", "")
        self._access_token = None

    @property
    def provider_name(self) -> str:
        return "auth0"

    def _get_management_token(self) -> str:
        if self._access_token:
            return self._access_token
        url = f"https://{self.domain}/oauth/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "audience": f"https://{self.domain}/api/v2/",
            "grant_type": "client_credentials",
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def search_user(self, email: str) -> Dict[str, Any]:
        """Search user by email in Auth0."""
        token = self._get_management_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://{self.domain}/api/v2/users-by-email?email={email}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        users = resp.json()
        if not users:
            return {"found": False, "user_id": None}
        return {"found": True, "user_id": users[0]["user_id"], "details": users[0]}

    def trigger_password_reset(self, email: str, client_id: str = None) -> Dict[str, Any]:
        """Triggers password reset ticket / email."""
        try:
            url = f"https://{self.domain}/dbconnections/change_password"
            payload = {"client_id": client_id or self.client_id, "email": email, "connection": "Username-Password-Authentication"}
            resp = requests.post(url, json=payload, timeout=5)
            if resp.status_code in (200, 201, 204):
                return {"status": "success", "email_sent": True, "message": resp.text}
            return {"status": "failed", "email_sent": False, "error": resp.text}
        except Exception as e:
            return {"status": "error", "email_sent": False, "error": str(e)}

    def unlock_user_account(self, user_id: str) -> Dict[str, Any]:
        """Deletes user blocks in Auth0."""
        try:
            token = self._get_management_token()
            headers = {"Authorization": f"Bearer {token}"}
            url = f"https://{self.domain}/api/v2/user-blocks/{user_id}"
            resp = requests.delete(url, headers=headers, timeout=5)
            return {"status": "unlocked" if resp.status_code == 204 else "failed", "user_id": user_id}
        except Exception as e:
            return {"status": "error", "user_id": user_id, "error": str(e)}

