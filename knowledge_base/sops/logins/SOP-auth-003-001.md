---
type: Playbook
sop_id: SOP-auth-003-001
title: Admin-Assisted User Password Reset
category: logins
target_os: null
description: Admin procedure to reset a user's password when self-service methods
  fail. Includes account verification, temporary password generation, and secure delivery
  instructions.
required_entities:
- email
- user_id
trigger_words:
- password reset
- admin reset
- temporary password
- account locked
steps:
- step_number: 1
  sop_step_description: Search for user account by email to confirm existence and
    identity
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
  sop_step_description: Verify user identity before proceeding with password reset
    (manual admin confirmation)
  step_type: verification
  provider: null
  function_name: null
  comm_inputs: null
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 0
  output_variable: identity_verified
  output_parse_instruction: Manual admin confirmation required. Set variables.identity_verified
    = 'true' if identity is confirmed, else 'false'.
  execute_if: variables.account_found == 'true'
  is_dangerous: false
  danger_warning: Do not proceed if user identity cannot be verified. Escalate to
    senior admin.
- step_number: 3
  sop_step_description: Reset user password and generate temporary password
  step_type: tool_call
  provider: mock_support_platform
  function_name: admin_reset_password
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: temporary_password
  timeout_seconds: 30
  output_variable: reset_success
  output_parse_instruction: If output contains 'reset_token' or 'message' indicating
    password reset token generated, set variables.reset_success = 'true' and store
    reset_token in variables.temp_password. If error, set variables.reset_success
    = 'false'.
  execute_if: variables.identity_verified == 'true'
  is_dangerous: true
  danger_warning: This action will force a password change for the user. Ensure identity
    is verified before proceeding.
- step_number: 4
  sop_step_description: Communicate temporary password to user via secure channel
  step_type: communication
  provider: system
  function_name: send_email
  comm_inputs:
    to_email: '{entities.email}'
    subject: Your Temporary Password
    body: 'Your temporary password is: {variables.temp_password}. Please change it
      immediately after logging in. Contact support if you did not request this change.'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: ok
  timeout_seconds: 30
  output_variable: email_result
  output_parse_instruction: If response.success.status is 'ok', set variables.email_sent
    = 'true'. If error, set variables.email_sent = 'false'.
  execute_if: variables.reset_success == 'true'
  is_dangerous: false
  danger_warning: Do not include the temporary password in the email body. Use a secure
    channel instead (e.g., phone call or secure password tool).
---

# Admin-Assisted User Password Reset Playbook

## Overview
Admin procedure to reset a user's password when self-service methods fail. Includes account verification, temporary password generation, and secure delivery instructions.

## Execution Steps
- **Step 1**: Search for user account by email to confirm existence and identity [Tool Call: `mock_support_platform.search_users({"email": "{entities.email}"})`]
- **Step 2**: Verify user identity before proceeding with password reset (manual admin confirmation) (`(none)`)
- **Step 3**: Reset user password and generate temporary password [Tool Call: `mock_support_platform.admin_reset_password({"user_id": "{variables.user_id}"})`]
- **Step 4**: Communicate temporary password to user via secure channel (`(none)`)
