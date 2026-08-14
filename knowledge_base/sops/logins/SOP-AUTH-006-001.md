---
type: Playbook
sop_id: SOP-AUTH-006-001
title: Disable Multi-Factor Authentication (MFA) for a User with Password Confirmation
category: logins
target_os: null
description: This playbook disables MFA for a user after confirming their current
  password, as required by the SOP. The user's password is verified by attempting
  a no-op password change, and MFA is disabled only if the password is confirmed.
knowledge_base_ref: []
required_entities:
- user_id
- current_password
trigger_words:
- disable MFA
- turn off MFA
- MFA removal
steps:
- step_number: 1
  sop_step_description: Verify the user's current password by attempting a no-op password
    change (current_password -> current_password). This confirms the password is correct
    without changing it.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: change_password
  comm_inputs:
    current_password: '{{entities.current_password}}'
    new_password: '{{entities.current_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Disable MFA for the user after password confirmation.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: disable_mfa
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.password_confirmed == 'true'
  timeout_seconds: 30
---

# Disable Multi-Factor Authentication (MFA) for a User with Password Confirmation Playbook

## Overview
This playbook disables MFA for a user after confirming their current password, as required by the SOP. The user's password is verified by attempting a no-op password change, and MFA is disabled only if the password is confirmed.

## Execution Steps
- **Step 1**: Verify the user's current password by attempting a no-op password change (current_password -> current_password). This confirms the password is correct without changing it. [Platform: `mock` | Tool Call: `l1_testing_platform_api.change_password({"current_password": "{{entities.current_password}}", "new_password": "{{entities.current_password}}"})`]
- **Step 2**: Disable MFA for the user after password confirmation. [Platform: `mock` | Tool Call: `l1_testing_platform_api.disable_mfa({})`]
