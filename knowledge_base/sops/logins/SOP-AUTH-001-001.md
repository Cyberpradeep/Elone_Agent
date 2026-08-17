---
type: Playbook
sop_id: SOP-AUTH-001-001
title: Unlock a User's Account
category: logins
target_os: null
description: This playbook automates the process of unlocking a user's account in
  the L1 Support Platform. It searches for the user by email, confirms their lock
  status, and unlocks the account if it is locked due to failed login attempts.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- unlock
- account
- login
- locked
steps:
- step_number: 1
  sop_step_description: Search for the user by email to confirm their existence and
    retrieve their user_id.
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
  sop_step_description: Retrieve detailed user profile to confirm lock status.
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
  execute_if: variables.account_found == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Unlock the user's account if it is locked due to failed login
    attempts.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: unlock_user_account
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.lock_status_confirmed == 'true' && variables.escalate_required
    != 'true'
  timeout_seconds: 30
---

# Unlock a User's Account Playbook

## Overview
This playbook automates the process of unlocking a user's account in the L1 Support Platform. It searches for the user by email, confirms their lock status, and unlocks the account if it is locked due to failed login attempts.

## Execution Steps
- **Step 1**: Search for the user by email to confirm their existence and retrieve their user_id. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Retrieve detailed user profile to confirm lock status. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Unlock the user's account if it is locked due to failed login attempts. [Platform: `mock` | Tool Call: `l1_testing_platform_api.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
