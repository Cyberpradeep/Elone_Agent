"""Agent A2: Deterministic Planning Subsystem (Module A6).

Provides:
- Step-to-Tool Binding Registry with two-person approval.
- Parameter provenance validation preventing LLM hallucinations.
- Deterministic ExecutionPlan compilation with canonical RFC 8785 plan hashing.
"""

from agents.a2_planning.bindings import (
    BindingRegistry,
    UnapprovedStepBindingError,
    compute_binding_hash,
)
from agents.a2_planning.provenance import (
    resolve_step_parameters,
    ParameterProvenanceViolationError,
)
from agents.a2_planning.planner import (
    DeterministicPlanner,
    determine_base_step_risk,
)

__all__ = [
    "BindingRegistry",
    "UnapprovedStepBindingError",
    "compute_binding_hash",
    "resolve_step_parameters",
    "ParameterProvenanceViolationError",
    "DeterministicPlanner",
    "determine_base_step_risk",
]
