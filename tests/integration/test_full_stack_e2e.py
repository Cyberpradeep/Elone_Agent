"""Pytest wrapper for Full-Stack End-to-End Enterprise Lifecycle Verification."""

import pytest
from scripts.run_e2e_full_stack_verification import run_full_stack_e2e_verification


def test_full_stack_enterprise_e2e_lifecycle():
    """Execute complete 9-stage end-to-end integration across all implemented modules."""
    success = run_full_stack_e2e_verification()
    assert success is True
