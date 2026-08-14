---
type: Playbook
sop_id: SOP-AUTH-004-001
title: How to Reset a User's MFA Device
category: logins
target_os: null
description: This playbook automates the process of resetting a user's Multi-Factor
  Authentication (MFA) device when they have lost or replaced their phone, or reinstalled
  their authenticator app, leading to lockout. It searches for the user, verifies
  their current MFA status, and if enabled, performs an MFA reset.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- reset mfa
- mfa device
- authenticator app
- lost phone
- replace phone
- mfa lockout
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to retrieve their profile
    and user ID.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: search_users
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Check the current MFA status for the found user to confirm
    if MFA is enabled. If MFA is already off, no reset is needed.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: get_user_details
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Perform the MFA reset for the user. This clears their old
    authenticator setup, prompting them to set up MFA again on their next login.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: admin_reset_mfa
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true' && variables.mfa_enabled == 'true'
  timeout_seconds: 30
---

# How to Reset a User's MFA Device Playbook

## Overview
This playbook automates the process of resetting a user's Multi-Factor Authentication (MFA) device when they have lost or replaced their phone, or reinstalled their authenticator app, leading to lockout. It searches for the user, verifies their current MFA status, and if enabled, performs an MFA reset.

## Execution Steps
- **Step 1**: Search for the user account by email to retrieve their profile and user ID. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Check the current MFA status for the found user to confirm if MFA is enabled. If MFA is already off, no reset is needed. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Perform the MFA reset for the user. This clears their old authenticator setup, prompting them to set up MFA again on their next login. [Platform: `mock` | Tool Call: `l1_testing_platform_api.admin_reset_mfa({"user_id": "{{variables.user_id}}"})`]
