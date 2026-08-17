---
type: Playbook
sop_id: SOP-AUTH-003
title: How to Reset a User's Password (Admin-Assisted)
category: logins
target_os: null
description: Admin-assisted password reset for users unable to use self-service, allowing
  direct temporary password setting or reset link generation based on admin choice.
knowledge_base_ref: []
required_entities:
- email
- reset_method_choice
trigger_words:
- reset password
- admin reset
- temporary password
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to confirm identity before
    making any changes.
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
  sop_step_description: Set a temporary password directly for the user, which is faster
    when the user is on a call.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: admin_reset_password
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true' and entities.reset_method_choice == 'direct'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Generate a password reset link for the user to use themselves.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: request_password_reset
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true' and entities.reset_method_choice == 'link'
  timeout_seconds: 30
---

# How to Reset a User's Password (Admin-Assisted) Playbook

## Overview
Admin-assisted password reset for users unable to use self-service, allowing direct temporary password setting or reset link generation based on admin choice.

## Execution Steps
- **Step 1**: Search for the user account by email to confirm identity before making any changes. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Set a temporary password directly for the user, which is faster when the user is on a call. [Platform: `mock` | Tool Call: `l1_testing_platform_api.admin_reset_password({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Generate a password reset link for the user to use themselves. [Platform: `mock` | Tool Call: `l1_testing_platform_api.request_password_reset({"email": "{{entities.email}}"})`]
