---
type: Playbook
sop_id: SOP-AUTH-006-001
title: Disable MFA for a User
category: logins
target_os: null
description: Disables Multi-Factor Authentication (MFA) for a user account after confirmed
  request, requiring the user's current password for security confirmation.
required_entities:
- email
trigger_words:
- disable MFA
- turn off MFA
- MFA removal
steps:
- step_number: 1
  sop_step_description: Confirm the user's request to disable MFA and their understanding
    of reduced account security. This step is verbal/ticket confirmation and not automated.
  step_type: communication
  provider: null
  function_name: null
  comm_inputs: null
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: null
  output_variable: null
  output_parse_instruction: null
  execute_if: null
  is_dangerous: false
  danger_warning: Ensure user confirmation is documented in the ticket before proceeding.
- step_number: 2
  sop_step_description: Disable MFA for the user via the support platform API.
  step_type: tool_call
  provider: mock_support_platform
  function_name: disable_mfa
  comm_inputs: {}
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: 'mfa_enabled": false'
  timeout_seconds: 30
  output_variable: disable_mfa_result
  output_parse_instruction: Inspect the JSON response. If 'success' is present and
    'mfa_enabled' is false, set 'mfa_disabled' to 'true'. If 'error' is present, set
    'mfa_disabled' to 'false' and store error details in variables.error_message.
  execute_if: null
  is_dangerous: true
  danger_warning: This action reduces account security. Ensure user confirmation is
    documented before execution.
- step_number: 3
  sop_step_description: Notify the user via email that MFA has been disabled and recommend
    re-enabling it later.
  step_type: tool_call
  provider: system
  function_name: send_email
  comm_inputs:
    to_email: '{entities.email}'
    subject: MFA Disabled for Your Account
    body: Multi-Factor Authentication (MFA) has been disabled for your account as
      requested. For security, we recommend re-enabling MFA once you have a working
      device. Contact support if you need assistance.
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: 'status": "ok"'
  timeout_seconds: 30
  output_variable: email_result
  output_parse_instruction: Inspect the JSON response. If 'success' is present, set
    'email_sent' to 'true'. If 'error' is present, set 'email_sent' to 'false' and
    store error details in variables.error_message.
  execute_if: variables.mfa_disabled == 'true'
  is_dangerous: false
  danger_warning: null
---

# Disable MFA for a User Playbook

## Overview
Disables Multi-Factor Authentication (MFA) for a user account after confirmed request, requiring the user's current password for security confirmation.

## Execution Steps
- **Step 1**: Confirm the user's request to disable MFA and their understanding of reduced account security. This step is verbal/ticket confirmation and not automated. (`(none)`)
- **Step 2**: Disable MFA for the user via the support platform API. [Tool Call: `mock_support_platform.disable_mfa({})`]
- **Step 3**: Notify the user via email that MFA has been disabled and recommend re-enabling it later. [Tool Call: `system.send_email({"to_email": "{entities.email}", "subject": "MFA Disabled for Your Account", "body": "Multi-Factor Authentication (MFA) has been disabled for your account as requested. For security, we recommend re-enabling MFA once you have a working device. Contact support if you need assistance."})`]
