---
type: Playbook
sop_id: SOP-auth-001-001
title: Unlock a User's Account
category: logins
target_os: null
description: Automated playbook to search for a locked user account, verify lock status,
  and unlock the account if it is a standard lockout. Escalates if the account is
  locked for security review.
required_entities:
- email
- user_id
trigger_words:
- unlock
- account
- locked
- login
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to confirm existence
    and retrieve user_id.
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
  sop_step_description: Retrieve detailed user profile to check lock status and confirm
    it is a standard lockout (not security review).
  step_type: tool_call
  provider: mock_support_platform
  function_name: get_user_details
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: locked
  timeout_seconds: 30
  output_variable: user_details
  output_parse_instruction: If response.success.locked is true and response.success.status
    is 'locked', set variables.lock_status = 'standard_lockout'. If response.success.status
    is 'Locked for security review', set variables.lock_status = 'security_review'
    and variables.needs_escalation = 'true'.
  execute_if: variables.account_found == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 3
  sop_step_description: Unlock the user account if it is a standard lockout. Reset
    failed login attempts to 0.
  step_type: tool_call
  provider: mock_support_platform
  function_name: unlock_user_account
  comm_inputs:
    user_id: '{variables.user_id}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: unlocked
  timeout_seconds: 30
  output_variable: unlock_result
  output_parse_instruction: If response.success.status is 'unlocked', set variables.unlock_success
    = 'true' and store response.success.user_id in variables.user_id. If response.error,
    set variables.unlock_success = 'false'.
  execute_if: variables.lock_status == 'standard_lockout' && variables.needs_escalation
    != 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 4
  sop_step_description: Send confirmation email to the user if unlock was successful.
  step_type: tool_call
  provider: system
  function_name: send_email
  comm_inputs:
    to_email: '{entities.email}'
    subject: Your Account Has Been Unlocked
    body: Your account has been unlocked. You can now log in. If you've forgotten
      your password, please use the password reset link.
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: ok
  timeout_seconds: 30
  output_variable: email_result
  output_parse_instruction: If response.success.status is 'ok', set variables.email_sent
    = 'true'.
  execute_if: variables.unlock_success == 'true'
  is_dangerous: false
  danger_warning: null
---

# Unlock a User's Account Playbook

## Overview
Automated playbook to search for a locked user account, verify lock status, and unlock the account if it is a standard lockout. Escalates if the account is locked for security review.

## Execution Steps
- **Step 1**: Search for the user account by email to confirm existence and retrieve user_id. [Tool Call: `mock_support_platform.search_users({"email": "{entities.email}"})`]
- **Step 2**: Retrieve detailed user profile to check lock status and confirm it is a standard lockout (not security review). [Tool Call: `mock_support_platform.get_user_details({"user_id": "{variables.user_id}"})`]
- **Step 3**: Unlock the user account if it is a standard lockout. Reset failed login attempts to 0. [Tool Call: `mock_support_platform.unlock_user_account({"user_id": "{variables.user_id}"})`]
- **Step 4**: Escalate the ticket if the account is locked for security review. (`(none)`)
- **Step 5**: Send confirmation email to the user if unlock was successful. [Tool Call: `system.send_email({"to_email": "{entities.email}", "subject": "Your Account Has Been Unlocked", "body": "Your account has been unlocked. You can now log in. If you've forgotten your password, please use the password reset link."})`]
