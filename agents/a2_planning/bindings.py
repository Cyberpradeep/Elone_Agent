"""Pre-Approved Step-to-Tool Binding Registry with Two-Person Approval.

Enforces:
- Edge Case 27: Unapproved step-to-tool binding halts planning with security error.
- Two-Person Approval Rule: process_owner_approver != security_reviewer_approver.
- Cryptographic binding hash verification via RFC 8785 canonical JSON.
"""

from typing import Dict, List, Optional, Tuple
from contracts.canonical import compute_canonical_hash, to_canonical_json
from contracts.plan import ParameterBinding, ParameterSourceEnum, StepBinding


class UnapprovedStepBindingError(Exception):
    """Raised when an unapproved or tampered step binding is encountered."""
    pass


def compute_binding_hash(
    sop_id: str,
    sop_version: str,
    step_number: int,
    tool_name: str,
    operation: str,
    parameter_bindings: List[ParameterBinding],
    process_owner_approver: str,
    security_reviewer_approver: str,
) -> str:
    """Computes authoritative SHA-256 hash for approved step-to-tool binding."""
    canonical_payload = {
        "sop_id": sop_id,
        "sop_version": sop_version,
        "step_number": step_number,
        "tool_name": tool_name,
        "operation": operation,
        "parameter_bindings": [pb.model_dump(mode="json") for pb in parameter_bindings],
        "process_owner_approver": process_owner_approver,
        "security_reviewer_approver": security_reviewer_approver,
    }
    return compute_canonical_hash(canonical_payload)


class BindingRegistry:
    """Registry of two-person approved step-to-tool bindings."""

    def __init__(self, register_defaults: bool = True):
        # Key: (sop_id, sop_version, step_number)
        self._bindings: Dict[Tuple[str, str, int], StepBinding] = {}
        if register_defaults:
            self._register_pilot_bindings()

    def register(self, binding: StepBinding) -> None:
        """Register an approved step binding, strictly validating two-person governance."""
        self.verify_binding_approval_or_raise(binding)
        key = (binding.sop_id, binding.sop_version, binding.step_number)
        self._bindings[key] = binding

    def get(self, sop_id: str, sop_version: str, step_number: int) -> Optional[StepBinding]:
        """Retrieve pre-approved binding, or None if not registered."""
        return self._bindings.get((sop_id, sop_version, step_number))

    def verify_binding_approval_or_raise(self, binding: StepBinding) -> None:
        """Verify two-person approval and canonical hash integrity."""
        # 1. Two-person rule: distinct approvers required
        if not binding.process_owner_approver or not binding.security_reviewer_approver:
            raise UnapprovedStepBindingError(
                f"Step binding for {binding.sop_id} step {binding.step_number} is missing required approvers"
            )
        if binding.process_owner_approver == binding.security_reviewer_approver:
            raise UnapprovedStepBindingError(
                f"Two-person rule violation for {binding.sop_id} step {binding.step_number}: "
                f"process owner '{binding.process_owner_approver}' cannot self-approve as security reviewer"
            )

        # 2. Canonical hash verification
        expected_hash = compute_binding_hash(
            sop_id=binding.sop_id,
            sop_version=binding.sop_version,
            step_number=binding.step_number,
            tool_name=binding.tool_name,
            operation=binding.operation,
            parameter_bindings=binding.parameter_bindings,
            process_owner_approver=binding.process_owner_approver,
            security_reviewer_approver=binding.security_reviewer_approver,
        )
        if binding.binding_hash != expected_hash:
            raise UnapprovedStepBindingError(
                f"Binding hash mismatch for {binding.sop_id} step {binding.step_number}: "
                f"expected '{expected_hash}', got '{binding.binding_hash}'"
            )

    def _register_pilot_bindings(self) -> None:
        """Pre-register default pre-approved bindings for pilot SOPs."""
        # SOP-WIN-014: Print Spooler (Step 1: Inspect, Step 2: Restart)
        b1_params = [
            ParameterBinding(
                param_name="name",
                source=ParameterSourceEnum.SOP_CONSTANT,
                source_key="name",
                static_value="Spooler",
            ),
            ParameterBinding(
                param_name="target_host",
                source=ParameterSourceEnum.TICKET_ENTITY,
                source_key="hostname",
            ),
        ]
        h1 = compute_binding_hash("SOP-WIN-014", "1.0.0", 1, "winrm_jea", "get_service", b1_params, "lead_ops@northwind.com", "sec_reviewer@northwind.com")
        self.register(StepBinding(
            sop_id="SOP-WIN-014", sop_version="1.0.0", step_number=1, tool_name="winrm_jea",
            operation="get_service", parameter_bindings=b1_params,
            process_owner_approver="lead_ops@northwind.com", security_reviewer_approver="sec_reviewer@northwind.com",
            binding_hash=h1,
        ))

        b2_params = [
            ParameterBinding(
                param_name="name",
                source=ParameterSourceEnum.SOP_CONSTANT,
                source_key="name",
                static_value="Spooler",
            ),
            ParameterBinding(
                param_name="target_host",
                source=ParameterSourceEnum.TICKET_ENTITY,
                source_key="hostname",
            ),
        ]
        h2 = compute_binding_hash("SOP-WIN-014", "1.0.0", 2, "winrm_jea", "restart_service", b2_params, "lead_ops@northwind.com", "sec_reviewer@northwind.com")
        self.register(StepBinding(
            sop_id="SOP-WIN-014", sop_version="1.0.0", step_number=2, tool_name="winrm_jea",
            operation="restart_service", parameter_bindings=b2_params,
            process_owner_approver="lead_ops@northwind.com", security_reviewer_approver="sec_reviewer@northwind.com",
            binding_hash=h2,
        ))
