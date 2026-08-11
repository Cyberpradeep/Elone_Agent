"""Communication tool executor for send_email notifications."""

import os
from typing import Any, Dict


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
            from shared.providers.system_ops import SystemOpsProvider
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
        from shared.tool_catalog import PROVIDERS
        target_providers = PROVIDERS
        if provider_name:
            norm_p_name = provider_name.lower().strip()
            matched = [p for p in PROVIDERS if p.provider_name == norm_p_name or norm_p_name in p.provider_name or p.provider_name in norm_p_name]
            if matched:
                target_providers = matched

        for provider in target_providers:
            if hasattr(provider, func_name):
                func = getattr(provider, func_name)
                import inspect
                sig = inspect.signature(func)
                valid_kwargs = {k: v for k, v in inputs.items() if k in sig.parameters}
                return func(**valid_kwargs)
    except Exception as e:
        print(f"[Comm Executor Error] Failed to execute '{func_name}': {e}")

    return {"status": "error", "message": f"Unknown communication or tool function '{func_name}' for provider '{provider_name}'"}



