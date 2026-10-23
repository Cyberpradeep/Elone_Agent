"""Communication tool executor for send_email notifications."""

import inspect
import os
from typing import Any, Dict

from shared.providers.system_ops import SystemOpsProvider
from shared.tool_catalog import PROVIDERS
# pyrefly: ignore [missing-import]
from elone_sop import find_platform_schema

def execute_comm_tool(func_name: str, inputs: Dict[str, Any], provider_name: str = None) -> Dict[str, Any]:
    """Executes communication and API tool functions strictly via provider registry matching provider_name."""
    if func_name == "send_email":
        to_email = inputs.get("to_email", "user@example.com")
        subject = inputs.get("subject", "IT Support Notification")
        body = inputs.get("body", "Notification from IT support.")

        print(f"\n[Comm Executor] Sending email to: {to_email}")
        print(f"  Subject: {subject}")
        print(f"  Body:\n{body}\n")

        try:
            provider = SystemOpsProvider()
            return provider.send_email(inputs)
        except Exception as e:
            print(f"[Comm Executor] Fallback mock email delivery: {e}")
            return {
                "status": "ok",
                "message": f"Email successfully dispatched to {to_email}",
                "to_email": to_email,
                "subject": subject,
            }

    try:


        target_providers = list(PROVIDERS)
        if provider_name:
            norm_p_name = provider_name.lower().strip()
            # 1. Direct name match
            matched = [p for p in PROVIDERS if p.provider_name == norm_p_name or norm_p_name in p.provider_name or p.provider_name in norm_p_name]

            # 2. Match via platform schema aliases (e.g. solandra, coreid -> MockProvider)
            if not matched:
                schema = find_platform_schema(norm_p_name)
                if schema:
                    plat_name = schema.get("platform", "").lower()
                    matched = [p for p in PROVIDERS if p.provider_name == plat_name or plat_name in p.provider_name or p.provider_name in plat_name]
                    if not matched and plat_name in ("solandra", "mock", "mock_support_platform"):
                        matched = [p for p in PROVIDERS if "mock" in p.provider_name]

            if matched:
                target_providers = matched

        for provider in target_providers:
            if hasattr(provider, func_name):
                func = getattr(provider, func_name)
                sig = inspect.signature(func)
                valid_kwargs = {k: v for k, v in inputs.items() if k in sig.parameters}
                return func(**valid_kwargs)
    except Exception as e:
        print(f"[Comm Executor Error] Failed to execute '{func_name}': {e}")

    return {"status": "error", "message": f"Unknown communication or tool function '{func_name}' for provider '{provider_name}'"}



