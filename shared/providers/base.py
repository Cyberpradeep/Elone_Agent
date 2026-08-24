from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseProvider(ABC):
    """Abstract base class for all tool providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g. 'auth0', 'okta', 'jira', 'mock')."""
        pass

    def get_tool_metadata(self) -> List[Dict[str, Any]]:
        """Optional tool schema metadata for providers."""
        return []

