"""
Agent A6: Reflection Rulebook Manager
=====================================
Frozen Specification: SOP Governance Hub v1.0 (Section 5.6)
Maintains auto-initialized Reflection Rulebooks under knowledge_base/patterns/<category>/rules_<SOP_ID>.md.
"""

from agents.a2_structuring.okf_builder import (
    _initialize_reflection_rulebook,
    _update_sops_catalog_indexes,
    _log_okf_creation,
)

__all__ = [
    "_initialize_reflection_rulebook",
    "_update_sops_catalog_indexes",
    "_log_okf_creation",
]
