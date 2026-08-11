---
type: Playbook
sop_id: SOP-auth-004-001
title: Reset User's MFA Device
category: logins
target_os: null
description: Automated playbook to reset a user's MFA device in the L1 Support Platform
  when they lose access to their authenticator app. Verifies account existence, checks
  current MFA status, and performs MFA reset if enabled.
required_entities:
- email
trigger_words:
- mfa
- reset
- authenticator
- lost phone
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to verify existence and
    retrieve user_id
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
  output_variable: search_result
  output_parse_instruction: If response.success.users array is not empty, set variables.account_found
    = 'true' and store response.success.users[0].id in variables.user_id. If empty,
    set variables.account_found = 'false'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Check current MFA status of the user to confirm MFA is enabled
  step_type: tool_call
  provider: mock_support_platform
  function_name: get_user_details
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: mfa_enabled
  timeout_seconds: 30
  output_variable: mfa_status
  output_parse_instruction: If response.success.mfa_enabled is true, set variables.mfa_enabled
    = 'true'. If false, set variables.mfa_enabled = 'false'.
  execute_if: variables.account_found == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 3
  sop_step_description: Reset the user's MFA device if MFA is currently enabled
  step_type: tool_call
  provider: mock_support_platform
  function_name: admin_reset_mfa
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: mfa_reset_success
  timeout_seconds: 90
  output_variable: reset_result
  output_parse_instruction: If response.success.status is 'mfa_reset_success', set
    variables.reset_success = 'true'. If error, set variables.reset_success = 'false'.
  execute_if: variables.mfa_enabled == 'true'
  is_dangerous: true
  danger_warning: This action will completely clear the user's MFA setup, requiring
    them to reconfigure MFA on next login.
- step_number: 4
  sop_step_description: Notify admin of completion status via email
  step_type: communication
  provider: system
  function_name: send_email
  comm_inputs:
    to_email: '{entities.admin_email}'
    subject: MFA Reset Completed for {entities.email}
    body: 'MFA reset for user {entities.email} has been completed. Status: {variables.reset_success}.
      User will need to set up MFA again on next login.'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: ok
  timeout_seconds: 30
  output_variable: email_result
  output_parse_instruction: If response.success.status is 'ok', set variables.email_sent
    = 'true'.
  execute_if: variables.reset_success == 'true'
  is_dangerous: false
  danger_warning: null
---

# Reset User's MFA Device Playbook

## Overview
Automated playbook to reset a user's MFA device in the L1 Support Platform when they lose access to their authenticator app. Verifies account existence, checks current MFA status, and performs MFA reset if enabled.

## Execution Steps
- **Step 1**: Search for the user account by email to verify existence and retrieve user_id [Tool Call: `mock_support_platform.search_users({"email": "{entities.email}"})`]
- **Step 2**: Check current MFA status of the user to confirm MFA is enabled [Tool Call: `mock_support_platform.get_user_details({"user_id": "{variables.user_id}"})`]
- **Step 3**: Reset the user's MFA device if MFA is currently enabled [Tool Call: `mock_support_platform.admin_reset_mfa({"user_id": "{variables.user_id}"})`]
- **Step 4**: Notify admin of completion status via email (`(none)`)
