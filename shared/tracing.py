import os
from typing import Optional


def setup_observability_tracing(project_name: str = "Elone_L1_Support_Agent") -> Optional[object]:
    """Configures LangSmith observability tracing for LangGraph workflow runs."""
    api_key = os.environ.get("LANGCHAIN_API_KEY")

    if api_key and api_key.strip():
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = project_name
        print(f"  [LangSmith Observability]: Tracing Active for project '{project_name}'")
        print(f"  [Live Dashboard]: https://smith.langchain.com")
    else:
        # Disable tracing if no API key is provided to prevent 401 Auth errors
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        print("  [Observability Info]: Set LANGCHAIN_API_KEY in .env to stream live agent traces to smith.langchain.com")
    return None
