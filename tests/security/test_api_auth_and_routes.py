"""Security & Contract Tests for Hardened API Routes (PR-15).

Verifies:
- Rule 1: Mandatory Bearer JWT on every route (401 on missing/invalid/expired).
- Rule 2: Server-side validation of approvals (clearance, quotas).
- Rule 3: Execution plans are strictly immutable (read-only).
- Edge Case 22: Cross-tenant isolation (403 on mismatched tenant).
- Edge Case 29: Self-approval forbidden (403 on requester == approver).
- Edge Case 30: 60-minute TTL expiry (410 on expired request).
"""

from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from api import (
    AuthenticatedUser,
    GLOBAL_APPROVAL_MANAGER,
    GLOBAL_PLAN_REGISTRY,
    create_access_token,
    create_api_app,
)
from approvals.engine import ApprovalManager
from contracts.plan import ExecutionPlan, ExecutionStep
from contracts.policy import RiskLevelEnum
from contracts.sop import SOPReference


@pytest.fixture(autouse=True)
def reset_registries():
    """Reset plan registry and approval manager state before each test."""
    GLOBAL_PLAN_REGISTRY.clear()
    GLOBAL_APPROVAL_MANAGER._requests.clear()
    GLOBAL_APPROVAL_MANAGER._records.clear()
    GLOBAL_APPROVAL_MANAGER._approver_lists.clear()
    yield


@pytest.fixture
def api_client():
    """Create a FastAPI test client with the versioned API app."""
    app = create_api_app()
    return TestClient(app)


def _create_sample_plan(
    issue_id: str = "INC-2041",
    risk_level: RiskLevelEnum = RiskLevelEnum.LEVEL_3_HIGH_MUTATION,
    tenant_id: str = "tenant-alpha",
) -> ExecutionPlan:
    """Helper to construct a valid ExecutionPlan contract model."""
    sop_ref = SOPReference(
        sop_id="SOP-WIN-014",
        version="1.0.0",
        canonical_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        title="Print Spooler Recovery",
        tenant_id=tenant_id,
    )
    step = ExecutionStep(
        step_number=1,
        title="Restart Print Spooler",
        tool_name="winrm",
        operation="restart_service",
        parameters={"service_name": "Spooler"},
        risk_level=risk_level,
        requires_approval=True,
    )
    return ExecutionPlan.create(issue_id=issue_id, sop=sop_ref, steps=[step])


# --- Test 1: Authentication Failures (Missing, Malformed, Expired) ---


def test_missing_auth_header_returns_401(api_client):
    """Anonymous requests must fail closed with HTTP 401 (Rule 1)."""
    resp = api_client.get("/api/v1/plans/INC-2041")
    assert resp.status_code == 401
    assert "MISSING_TOKEN" in resp.json()["detail"]


def test_invalid_token_returns_401(api_client):
    """Malformed or forged tokens must fail closed with HTTP 401."""
    resp = api_client.get(
        "/api/v1/plans/INC-2041",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert resp.status_code == 401
    assert "INVALID_TOKEN" in resp.json()["detail"]


def test_expired_token_returns_401(api_client):
    """Expired tokens must fail closed with HTTP 401."""
    user = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    expired_token = create_access_token(user, expires_delta=timedelta(minutes=-5))
    resp = api_client.get(
        "/api/v1/plans/INC-2041",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401
    assert "EXPIRED_TOKEN" in resp.json()["detail"]


# --- Test 2: Tenant Isolation (Edge Case 22) ---


def test_cross_tenant_plan_access_blocked_403(api_client):
    """User from tenant-beta cannot view plans belonging to tenant-alpha (EC-22)."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    beta_user = AuthenticatedUser(
        user_id="op-intruder",
        tenant_id="tenant-beta",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(beta_user)

    resp = api_client.get(
        "/api/v1/plans/INC-2041",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "CROSS_TENANT_ACCESS_FORBIDDEN" in resp.json()["detail"]


def test_plan_retrieval_success_200(api_client):
    """Authorized user in same tenant receives immutable ExecutionPlan contract."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    alpha_user = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(alpha_user)

    resp = api_client.get(
        "/api/v1/plans/INC-2041",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue_id"] == "INC-2041"
    assert data["plan_hash"] == plan.plan_hash
    assert len(data["steps"]) == 1


# --- Test 3: Plan Immutability (Rule 3) ---


def test_plan_immutable_rejects_put_patch_405(api_client):
    """Plans cannot be updated or patched via API; must yield 405 Method Not Allowed (Rule 3)."""
    alpha_user = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(alpha_user)
    headers = {"Authorization": f"Bearer {token}"}

    put_resp = api_client.put("/api/v1/plans/INC-2041", headers=headers, json={"steps": []})
    assert put_resp.status_code == 405

    patch_resp = api_client.patch("/api/v1/plans/INC-2041", headers=headers, json={"steps": []})
    assert patch_resp.status_code == 405


# --- Test 4: Separation of Duties (Edge Case 29) ---


def test_self_approval_forbidden_403(api_client):
    """Requester attempting to approve their own plan raises 403 SELF_APPROVAL_FORBIDDEN (EC-29)."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    requester_user = AuthenticatedUser(
        user_id="user-alice",
        tenant_id="tenant-alpha",
        roles=["requester"],
        clearance=3,
    )
    token = create_access_token(requester_user)

    resp = api_client.post(
        "/api/v1/plans/INC-2041/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": plan.plan_hash},
    )
    assert resp.status_code == 403
    assert "SELF_APPROVAL_FORBIDDEN" in resp.json()["detail"]


# --- Test 5: Plan Hash Verification ---


def test_plan_hash_mismatch_returns_409(api_client):
    """Submitting approval with wrong plan_hash fails closed with 409 Conflict."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(approver)

    resp = api_client.post(
        "/api/v1/plans/INC-2041/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": "a" * 64},  # Forged hash
    )
    assert resp.status_code == 409
    assert "PLAN_HASH_MISMATCH" in resp.json()["detail"]


# --- Test 6: Clearance Check ---


def test_insufficient_clearance_returns_403(api_client):
    """Approver with lower clearance than step risk level is rejected with HTTP 403."""
    plan = _create_sample_plan(issue_id="INC-2041", risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION)
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    junior_user = AuthenticatedUser(
        user_id="op-trainee",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=1,  # Clearance 1 < Risk Level 3
    )
    token = create_access_token(junior_user)

    resp = api_client.post(
        "/api/v1/plans/INC-2041/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": plan.plan_hash},
    )
    assert resp.status_code == 403
    assert "INSUFFICIENT_CLEARANCE" in resp.json()["detail"]


# --- Test 7: Level 3 Single Approval Success ---


def test_level_3_single_approval_success_200(api_client):
    """Authorized non-requester approves Level 3 plan -> HTTP 200 APPROVED."""
    plan = _create_sample_plan(issue_id="INC-2041", risk_level=RiskLevelEnum.LEVEL_3_HIGH_MUTATION)
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["lead_operator"],
        clearance=3,
    )
    token = create_access_token(approver)

    resp = api_client.post(
        "/api/v1/plans/INC-2041/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": plan.plan_hash, "comments": "Approved after reviewing step bindings"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_authorized"] is True
    assert data["approval_record"]["status"] == "APPROVED"
    assert data["approval_record"]["approver_ids"] == ["op-pradeep-01"]


# --- Test 8: Level 4 Dual-Approver Workflow ---


def test_level_4_dual_approval_workflow(api_client):
    """Level 4 critical mutation requires two distinct approvers."""
    plan = _create_sample_plan(issue_id="INC-2042", risk_level=RiskLevelEnum.LEVEL_4_CRITICAL)
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2042",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver_1 = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["lead_operator"],
        clearance=4,
    )
    approver_2 = AuthenticatedUser(
        user_id="lead-latha-01",
        tenant_id="tenant-alpha",
        roles=["security_architect"],
        clearance=4,
    )
    token_1 = create_access_token(approver_1)
    token_2 = create_access_token(approver_2)

    # First signoff: Status remains PENDING
    resp_1 = api_client.post(
        "/api/v1/plans/INC-2042/approve",
        headers={"Authorization": f"Bearer {token_1}"},
        json={"plan_hash": plan.plan_hash},
    )
    assert resp_1.status_code == 200
    assert resp_1.json()["is_authorized"] is False
    assert resp_1.json()["approval_record"]["status"] == "PENDING"
    assert resp_1.json()["approval_record"]["approver_ids"] == ["op-pradeep-01"]

    # Second signoff by distinct approver: Status becomes APPROVED
    resp_2 = api_client.post(
        "/api/v1/plans/INC-2042/approve",
        headers={"Authorization": f"Bearer {token_2}"},
        json={"plan_hash": plan.plan_hash},
    )
    assert resp_2.status_code == 200
    assert resp_2.json()["is_authorized"] is True
    assert resp_2.json()["approval_record"]["status"] == "APPROVED"
    assert resp_2.json()["approval_record"]["approver_ids"] == ["op-pradeep-01", "lead-latha-01"]


# --- Test 9: 60-Minute Approval TTL Expiration (Edge Case 30) ---


def test_approval_expired_ttl_returns_410(api_client):
    """Approval attempt after 60-minute window yields HTTP 410 Gone (EC-30)."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(approver)

    # Manually create request with past expiration
    req = GLOBAL_APPROVAL_MANAGER.create_request(plan=plan, requester_id="user-alice")
    # Expire it manually in manager
    past_time = datetime.utcnow() + timedelta(minutes=65)
    with pytest.raises(Exception):
        GLOBAL_APPROVAL_MANAGER.submit_approval(
            request_id=req.request_id,
            approver_id="op-test",
            current_time=past_time,
        )

    # Attempt to approve via API returns 410
    resp = api_client.post(
        "/api/v1/plans/INC-2041/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": plan.plan_hash},
    )
    assert resp.status_code == 410
    assert "APPROVAL_EXPIRED" in resp.json()["detail"]


# --- Test 10: Operator Rejection Halts Execution ---


def test_operator_rejection_halts_plan_200(api_client):
    """Operator rejection marks record as REJECTED and execution unauthorized."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(approver)

    resp = api_client.post(
        "/api/v1/plans/INC-2041/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"plan_hash": plan.plan_hash, "reason": "Target hostname is undergoing maintenance"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_authorized"] is False
    assert data["approval_record"]["status"] == "REJECTED"
    assert data["approval_record"]["rejection_reason"] == "Target hostname is undergoing maintenance"


# --- Test 11: GET Approvals Endpoint ---


def test_get_plan_approvals_endpoint(api_client):
    """GET /api/v1/plans/{issue_id}/approvals returns request and record metadata."""
    plan = _create_sample_plan(issue_id="INC-2041")
    GLOBAL_PLAN_REGISTRY.register_plan(
        issue_id="INC-2041",
        plan=plan,
        tenant_id="tenant-alpha",
        requester_id="user-alice",
    )

    approver = AuthenticatedUser(
        user_id="op-pradeep-01",
        tenant_id="tenant-alpha",
        roles=["operator"],
        clearance=3,
    )
    token = create_access_token(approver)

    resp = api_client.get(
        "/api/v1/plans/INC-2041/approvals",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue_id"] == "INC-2041"
    assert data["plan_hash"] == plan.plan_hash
    assert data["request"]["requester_id"] == "user-alice"
    assert data["is_authorized"] is False
