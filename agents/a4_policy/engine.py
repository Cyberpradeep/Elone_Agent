"""Plan-Wide Policy & Risk Rules Engine (Module A7).

Enforces:
- Automatic +1 risk elevation for PROD environments.
- One-Way LLM Advisory rule (LLM advisory can elevate risk, never lower code risk).
- Mandatory human approval for Level 3 (1 approver) and Level 4 (2 approvers).
- Re-compilation of ExecutionPlan with authoritative evaluated risk levels.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict
from contracts.policy import EnvironmentEnum, PolicyDecision, RiskLevelEnum, evaluate_step_risk
from contracts.plan import ExecutionPlan, ExecutionStep
from agents.a4_policy.rules import get_operation_base_risk


class PlanPolicyEvaluation(BaseModel):
    """Aggregate policy evaluation outcome for an ExecutionPlan."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_hash: str
    step_decisions: List[PolicyDecision]
    overall_risk: RiskLevelEnum
    requires_human_approval: bool
    required_approver_count: int
    evaluated_plan: ExecutionPlan


class PolicyEngine:
    """Evaluates declarative policies and risk models across full execution plans."""

    def evaluate_plan(
        self,
        plan: ExecutionPlan,
        environment: EnvironmentEnum,
        llm_advisories: Optional[Dict[int, RiskLevelEnum]] = None,
    ) -> PlanPolicyEvaluation:
        """Evaluate plan steps against enterprise policy, environment elevation, and LLM advisory."""
        advisories = llm_advisories or {}
        step_decisions: List[PolicyDecision] = []
        evaluated_steps: List[ExecutionStep] = []

        for step in plan.steps:
            # 1. Resolve deterministic code base risk
            code_base_risk = get_operation_base_risk(step.tool_name, step.operation)
            # If the step already had a higher declared risk, respect the higher baseline
            base_risk = max(code_base_risk, step.risk_level)

            # 2. Check for optional LLM advisory risk on this step
            llm_advisory = advisories.get(step.step_number)

            # 3. Authoritative step evaluation (enforcing PROD +1 and One-Way LLM advisory)
            decision = evaluate_step_risk(
                step_number=step.step_number,
                base_risk=base_risk,
                environment=environment,
                llm_advisory_risk=llm_advisory,
                base_reason=f"Tool '{step.tool_name}' operation '{step.operation}' base risk {base_risk.name}",
            )
            step_decisions.append(decision)

            # 4. Construct updated step with evaluated risk and approval governance flags
            evaluated_step = ExecutionStep(
                step_number=step.step_number,
                title=step.title,
                tool_name=step.tool_name,
                operation=step.operation,
                parameters=step.parameters,
                risk_level=decision.evaluated_risk,
                rollback_step=step.rollback_step,
                timeout_seconds=step.timeout_seconds,
                requires_approval=decision.requires_approval,
            )
            evaluated_steps.append(evaluated_step)

        # 5. Aggregate overall plan risk and approval requirements
        overall_risk = max(d.evaluated_risk for d in step_decisions)
        requires_human_approval = any(d.requires_approval for d in step_decisions)
        required_approver_count = max(d.required_approver_count for d in step_decisions)

        # 6. Reconstruct validated ExecutionPlan with evaluated steps
        evaluated_plan = ExecutionPlan.create(
            issue_id=plan.issue_id,
            sop=plan.sop,
            steps=evaluated_steps,
        )

        return PlanPolicyEvaluation(
            plan_hash=evaluated_plan.plan_hash,
            step_decisions=step_decisions,
            overall_risk=overall_risk,
            requires_human_approval=requires_human_approval,
            required_approver_count=required_approver_count,
            evaluated_plan=evaluated_plan,
        )
