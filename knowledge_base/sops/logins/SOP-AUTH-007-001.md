---
type: Playbook
sop_id: SOP-AUTH-007-001
title: Handle Suspicious Login Report
category: logins
target_os: null
description: Procedure to lock a user account and escalate to security team upon receiving
  a suspicious login report. Includes steps to review audit logs and prevent further
  access during investigation.
required_entities:
- user_id
- email
trigger_words:
- suspicious login
- security alert
- unusual activity
- account lock
steps:
- step_number: 1
  sop_step_description: Search for the user account to confirm existence and retrieve
    user_id.
  step_type: tool_call
  provider: mock_support_platform
  function_name: search_users
  comm_inputs:
    email: '{entities.email}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: users
  timeout_seconds: 30
  output_variable: user_search_result
  output_parse_instruction: If response.success.users array is not empty, set variables.account_found
    = 'true' and store response.success.users[0].id in variables.user_id. If not found,
    set variables.account_found = 'false'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Retrieve the user's audit log to review recent login activity
    for suspicious entries.
  step_type: tool_call
  provider: mock_support_platform
  function_name: get_user_audit_log
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: logs
  timeout_seconds: 90
  output_variable: audit_log_result
  output_parse_instruction: Store the entire logs array in variables.audit_logs for
    later use in escalation. Flag any log entries with action='login' and unusual
    timestamps or locations.
  execute_if: variables.account_found == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 3
  sop_step_description: Lock the user account as a precaution to prevent further access
    during investigation.
  step_type: tool_call
  provider: mock_support_platform
  function_name: lock_user_account
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: locked
  timeout_seconds: 30
  output_variable: lock_result
  output_parse_instruction: If response.success.status is 'locked', set variables.account_locked
    = 'true'. If error, set variables.account_locked = 'false'.
  execute_if: variables.account_found == 'true'
  is_dangerous: true
  danger_warning: This action will immediately revoke all access for the user. Ensure
    this is a security incident before proceeding.
- step_number: 4
  sop_step_description: Notify the security team with the audit log details for further
    investigation.
  step_type: communication
  provider: null
  function_name: null
  comm_inputs: null
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 30
  output_variable: escalation_result
  output_parse_instruction: Use the system.send_email function to send the audit log
    details to the security team. Include variables.audit_logs in the email body.
  execute_if: variables.account_locked == 'true'
  is_dangerous: false
  danger_warning: null
---

# Handle Suspicious Login Report Playbook

## Overview
Procedure to lock a user account and escalate to security team upon receiving a suspicious login report. Includes steps to review audit logs and prevent further access during investigation.

## Execution Steps
- **Step 1**: Search for the user account to confirm existence and retrieve user_id. [Tool Call: `mock_support_platform.search_users({"email": "{entities.email}"})`]
- **Step 2**: Retrieve the user's audit log to review recent login activity for suspicious entries. [Tool Call: `mock_support_platform.get_user_audit_log({"user_id": "{variables.user_id}"})`]
- **Step 3**: Lock the user account as a precaution to prevent further access during investigation. [Tool Call: `mock_support_platform.lock_user_account({"user_id": "{variables.user_id}"})`]
- **Step 4**: Notify the security team with the audit log details for further investigation. (`(none)`)
