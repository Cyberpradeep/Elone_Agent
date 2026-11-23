"""Parameter Provenance Validation & Origin Enforcement.

Enforces:
- Edge Case 28: Parameter provenance violation rejects plan (zero LLM hallucinations).
- Parameter origins restricted strictly to:
  * TICKET_ENTITY (extracted entities from incident ticket)
  * CMDB_LOOKUP (authoritative asset management records)
  * SOP_CONSTANT (pre-approved immutable constants in SOP binding)
  * PREVIOUS_STEP_OUTPUT (deterministic output variables from earlier steps)
"""

from typing import Any, Dict, List, Optional
from contracts.plan import ParameterBinding, ParameterSourceEnum, StepBinding


class ParameterProvenanceViolationError(Exception):
    """Raised when a parameter fails provenance check or originates from unvalidated input."""
    pass


def resolve_step_parameters(
    binding: StepBinding,
    entities: Dict[str, Any],
    cmdb_context: Optional[Dict[str, Any]] = None,
    previous_outputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve and validate parameter values against authoritative provenance origins.

    Fails closed if any required parameter cannot be traced to an approved source.
    """
    resolved_params: Dict[str, Any] = {}
    cmdb_data = cmdb_context or {}
    prev_data = previous_outputs or {}

    for pb in binding.parameter_bindings:
        val: Any = None

        if pb.source == ParameterSourceEnum.SOP_CONSTANT:
            if pb.static_value is None:
                raise ParameterProvenanceViolationError(
                    f"Parameter '{pb.param_name}' is marked SOP_CONSTANT but has no static_value defined "
                    f"for {binding.sop_id} step {binding.step_number}"
                )
            val = pb.static_value

        elif pb.source == ParameterSourceEnum.TICKET_ENTITY:
            if pb.source_key not in entities:
                raise ParameterProvenanceViolationError(
                    f"Provenance violation: Required ticket entity '{pb.source_key}' for parameter "
                    f"'{pb.param_name}' not found in incident entities for {binding.sop_id} step {binding.step_number}"
                )
            val = entities[pb.source_key]

        elif pb.source == ParameterSourceEnum.CMDB_LOOKUP:
            if pb.source_key in cmdb_data:
                val = cmdb_data[pb.source_key]
            elif pb.source_key in entities:
                val = entities[pb.source_key]
            else:
                raise ParameterProvenanceViolationError(
                    f"Provenance violation: Required CMDB asset record '{pb.source_key}' for parameter "
                    f"'{pb.param_name}' not found in CMDB context or entities"
                )

        elif pb.source == ParameterSourceEnum.PREVIOUS_STEP_OUTPUT:
            if pb.source_key in prev_data:
                val = prev_data[pb.source_key]
            else:
                # During static planning, mark placeholder reference for runtime resolution
                val = f"${{steps.{pb.source_key}}}"

        else:
            raise ParameterProvenanceViolationError(
                f"Unknown parameter source '{pb.source}' for parameter '{pb.param_name}'"
            )

        resolved_params[pb.param_name] = val

    return resolved_params
