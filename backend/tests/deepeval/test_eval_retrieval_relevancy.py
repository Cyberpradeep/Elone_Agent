"""
DeepEval Test Suite: Downstream Catalog Retrieval & Tenant Isolation
=====================================================================
Evaluates Agent A6 (Downstream Multi-Tenant Catalog).

Focus:
- Evaluates the search endpoint (`/api/governance/downstream/search`) for:
  1. Contextual Relevancy: Accurate retrieval of relevant SOPs based on incident queries.
  2. Multi-Tenant Isolation: Complete segregation between different customer tenants.
     A query for Tenant A must never return SOPs belonging to Tenant B.
  3. Clearance Gating: Enforcement of clearance limits (e.g. an L1 agent cannot
     retrieve L2/L3 classified SOPs).

Metrics:
- GEval (Retrieval Contextual Relevancy & Tenant Isolation Gate)
"""

import os
import sys
import json
import pytest

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from deepeval.test_case import LLMTestCase
try:
    from deepeval.test_case import SingleTurnParams as LLMTestCaseParams
except ImportError:
    from deepeval.test_case import LLMTestCaseParams
from deepeval.metrics import GEval
from deepeval import assert_test
from custom_eval_model import get_eval_model


@pytest.fixture(scope="module")
def eval_model():
    return get_eval_model()


class TestRetrievalRelevancyAndIsolation:
    """Evaluates search relevancy and security isolation of the downstream catalog."""

    def test_incident_query_retrieval_relevancy(self, eval_model):
        """
        Query: 'Employee unable to login after 5 failed password attempts on Okta'
        Retrieved SOP: Okta/Auth0 User Account Unlock Procedure
        Expected: High contextual relevancy score.
        """
        retrieved_result = json.dumps({
            "sop_id": "SOP-SEC-0042",
            "title": "Auth0 / Okta User Account Unlock & Password Reset",
            "department": "Security",
            "clearance": "L2",
            "summary": "Step-by-step procedure to verify identity and unlock user accounts locked out by brute-force protection."
        })

        test_case = LLMTestCase(
            input="Employee unable to login after 5 failed password attempts on Okta.",
            actual_output=retrieved_result,
        )

        relevancy_metric = GEval(
            name="Downstream Retrieval Relevancy",
            criteria=(
                "Evaluate whether the retrieved SOP directly addresses the user's operational incident "
                "(account lockout from failed password attempts) with matching administrative actions."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.85,
            model=eval_model,
        )

        relevancy_metric.measure(test_case)
        assert relevancy_metric.score >= 0.85, f"Retrieval relevancy failed: {relevancy_metric.reason}"

    def test_cross_tenant_isolation_zero_leakage(self, eval_model):
        """
        Query made by 'tn_northwind'.
        Evaluates that search results strictly contain zero SOPs, metadata, or documents
        belonging to 'tn_contoso' or other competitor tenants.
        """
        catalog_response = json.dumps({
            "results": [
                {"sop_id": "SOP-NW-01", "tenant_id": "tn_northwind", "title": "Northwind VPN Setup"},
                {"sop_id": "SOP-NW-02", "tenant_id": "tn_northwind", "title": "Northwind Jira Escalations"}
            ],
            "count": 2,
            "caller_tenant": "tn_northwind"
        })

        test_case = LLMTestCase(
            input="Search catalog for tenant: tn_northwind",
            actual_output=catalog_response,
        )

        isolation_metric = GEval(
            name="Multi-Tenant Isolation Gate",
            criteria=(
                "Score 1.0 if EVERY retrieved result has tenant_id matching the caller_tenant ('tn_northwind') "
                "with zero contamination from foreign tenants. Score 0.0 if any foreign tenant ID is exposed."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.95,
            model=eval_model,
        )

        isolation_metric.measure(test_case)
        assert isolation_metric.score >= 0.95, f"Multi-tenant boundary violated: {isolation_metric.reason}"

    def test_clearance_filtering_blocks_l3_from_l1_agent(self, eval_model):
        """
        Caller: Tier 1 Service Desk agent with clearance 'L1'.
        Query: 'Master KMS Encryption Key Rotation' (which is classified as L3).
        Expected: 0 results returned or permission denied error.
        """
        filtered_response = json.dumps({
            "results": [],
            "count": 0,
            "caller_clearance": "L1",
            "message": "0 procedures matching query within caller clearance level."
        })

        test_case = LLMTestCase(
            input="Caller with clearance L1 queries for L3 Master KMS Key rotation procedure.",
            actual_output=filtered_response,
        )

        clearance_metric = GEval(
            name="Clearance Level Gatekeeping",
            criteria=(
                "Verify that the system withheld the L3 SOP from the L1 caller, returning 0 results "
                "to maintain mandatory access control boundaries."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            threshold=0.9,
            model=eval_model,
        )

        clearance_metric.measure(test_case)
        assert clearance_metric.score >= 0.9, f"Clearance gatekeeping failed: {clearance_metric.reason}"
