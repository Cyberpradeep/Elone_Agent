---
type: Playbook
sop_id: SOP-AUTH-004
title: How to Reset a User's MFA Device
category: logins
target_os: windows
description: This playbook automates the process of resetting a user's Multi-Factor
  Authentication (MFA) device when they lose or replace their phone, ensuring they
  can regain access to their account.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- mfa
- reset
- authenticator
- login
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to retrieve their user
    ID.
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
  sop_step_description: Retrieve the user's detailed profile to check their current
    MFA status.
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
  sop_step_description: Reset the user's MFA device, clearing their old authenticator
    setup.
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
  execute_if: variables.user_found == 'true' and variables.mfa_enabled_status == 'true'
  timeout_seconds: 30
---

# How to Reset a User's MFA Device Playbook

## Overview
This playbook automates the process of resetting a user's Multi-Factor Authentication (MFA) device when they lose or replace their phone, ensuring they can regain access to their account.

## Execution Steps
- **Step 1**: Search for the user account by email to retrieve their user ID. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Retrieve the user's detailed profile to check their current MFA status. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Reset the user's MFA device, clearing their old authenticator setup. [Platform: `mock` | Tool Call: `l1_testing_platform_api.admin_reset_mfa({"user_id": "{{variables.user_id}}"})`]
