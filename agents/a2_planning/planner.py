"""Deterministic Execution Planning Agent (Module A6).

Constructs immutable ExecutionPlan contract models by:
- Binding SOP steps strictly to pre-approved StepBindings (Edge Case 27).
- Resolving parameters via validated provenance (Edge Case 28).
- Computing deterministic RFC 8785 canonical plan hashes.
- Preventing LLM shell command hallucination (Rule 4).
"""

from typing import Any, Dict, List, Optional
from contracts.issue import Issue
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.policy import RiskLevelEnum
from contracts.sop import SignedSOPPayload
from agents.a2_planning.bindings import BindingRegistry, UnapprovedStepBindingError
from agents.a2_planning.provenance import resolve_step_parameters, ParameterProvenanceViolationError


READONLY_OPERATIONS = {"get_service", "query_service", "nslookup", "agent_health", "check_sql", "ping", "read_log"}
LOW_MUTATION_OPERATIONS = {"flush_dns", "clear_cache"}
HIGH_MUTATION_OPERATIONS = {"restart_service", "stop_service", "kill_process", "run_backup"}


def determine_base_step_risk(operation: str) -> RiskLevelEnum:
    """Deterministically map tool operation name to baseline risk level."""
    op_clean = operation.lower().strip()
    if op_clean in READONLY_OPERATIONS:
        return RiskLevelEnum.LEVEL_1_READONLY
    if op_clean in LOW_MUTATION_OPERATIONS:
        return RiskLevelEnum.LEVEL_2_LOW_MUTATION
    if op_clean in HIGH_MUTATION_OPERATIONS:
        return RiskLevelEnum.LEVEL_3_HIGH_MUTATION
    # Default to Level 3 High Mutation for unspecified state modifications
    return RiskLevelEnum.LEVEL_3_HIGH_MUTATION


class DeterministicPlanner:
    """Builds deterministic, canonically hashed ExecutionPlans from approved bindings."""

    def __init__(self, registry: Optional[BindingRegistry] = None):
        self.registry = registry or BindingRegistry()

    def build_plan(
        self,
        issue: Issue,
        sop: SignedSOPPayload,
        cmdb_context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """Construct immutable ExecutionPlan bound to exact SOP version.

        Fails closed if:
        1. SOP contains no steps.
        2. Any step has no pre-approved StepBinding registered (Edge Case 27).
        3. Any parameter fails provenance validation (Edge Case 28).
        """
        raw_steps: List[Dict[str, Any]] = sop.body_json.get("steps", [])
        if not raw_steps:
            raise ValueError(f"SOP '{sop.sop.sop_id}' contains zero execution steps")

        execution_steps: List[ExecutionStep] = []

        for idx, raw_step in enumerate(raw_steps, start=1):
            step_num = raw_step.get("step") or raw_step.get("step_number") or idx
            title = raw_step.get("title", f"Step {step_num}")
            sop_id = sop.sop.sop_id
            sop_ver = sop.sop.version

            # 1. Fetch and verify pre-approved binding (Edge Case 27)
            binding = self.registry.get(sop_id, sop_ver, step_num)
            if not binding:
                raise UnapprovedStepBindingError(
                    f"Security violation: No approved step binding registered for {sop_id} v{sop_ver} "
                    f"step {step_num} (Edge Case 27: Unapproved step binding)"
                )

            self.registry.verify_binding_approval_or_raise(binding)

            # 2. Resolve parameter provenance (Edge Case 28)
            resolved_params = resolve_step_parameters(
                binding=binding,
                entities=issue.entities,
                cmdb_context=cmdb_context,
            )

            # 3. Determine baseline risk
            risk_level = determine_base_step_risk(binding.operation)

            # 4. Construct ExecutionStep
            step = ExecutionStep(
                step_number=step_num,
                title=title,
                tool_name=binding.tool_name,
                operation=binding.operation,
                parameters=resolved_params,
                risk_level=risk_level,
                timeout_seconds=raw_step.get("timeout_seconds", 30),
                requires_approval=risk_level >= RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
            )
            execution_steps.append(step)

        # 5. Build ExecutionPlan with deterministic canonical plan_hash
        return ExecutionPlan.create(
            issue_id=issue.issue_id,
            sop=sop.sop,
            steps=execution_steps,
        )
