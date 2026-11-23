"""End-to-End Integration Suite for Pilot Scenarios."""

import pytest
from scripts.demo_e2e_pilot import (
    run_scenario_1_shadow_mode,
    run_scenario_2_supervised_mode_approval,
    run_scenario_3_supervised_mode_rejection,
    run_scenario_4_policy_based_selective_autonomy,
    run_scenario_5_pre_step_guard_security,
    run_scenario_6_emergency_kill_switch,
    run_scenario_7_demo_reset_issue,
)


def test_e2e_scenario_1_shadow_mode():
    run_scenario_1_shadow_mode()


def test_e2e_scenario_2_supervised_mode_approval():
    run_scenario_2_supervised_mode_approval()


def test_e2e_scenario_3_supervised_mode_rejection():
    run_scenario_3_supervised_mode_rejection()


def test_e2e_scenario_4_policy_based_selective_autonomy():
    run_scenario_4_policy_based_selective_autonomy()


def test_e2e_scenario_5_pre_step_guard_security():
    run_scenario_5_pre_step_guard_security()


def test_e2e_scenario_6_emergency_kill_switch():
    run_scenario_6_emergency_kill_switch()


def test_e2e_scenario_7_demo_reset_issue():
    run_scenario_7_demo_reset_issue()
