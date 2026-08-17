---
type: Playbook
sop_id: SOP-AUTH-001
title: How to Unlock a User's Account
category: logins
target_os: windows
description: This playbook automates the process of unlocking a user's account on
  the L1 Support Platform after repeated failed login attempts, ensuring quick resolution
  and preventing duplicate tickets. It includes steps to search for the user, confirm
  their lock status, and perform the unlock action, with a check for security review
  locks that require escalation.
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
  sop_step_description: Search for the user's account using their email address on
    the Admin Dashboard. If multiple results appear, confirm the correct user by full
    name.
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
  sop_step_description: Retrieve the user's detailed profile to check their account
    status. If the status indicates 'Locked for security review', the process should
    stop and be escalated.
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
  execute_if: variables.user_id != null
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Unlock the user's account. The status badge should change
    to 'Active', and failed login attempts should reset to 0.
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
  execute_if: variables.account_locked == 'true' and variables.security_review_lock
    != 'true'
  timeout_seconds: 30
---

# How to Unlock a User's Account Playbook

## Overview
This playbook automates the process of unlocking a user's account on the L1 Support Platform after repeated failed login attempts, ensuring quick resolution and preventing duplicate tickets. It includes steps to search for the user, confirm their lock status, and perform the unlock action, with a check for security review locks that require escalation.

## Execution Steps
- **Step 1**: Search for the user's account using their email address on the Admin Dashboard. If multiple results appear, confirm the correct user by full name. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Retrieve the user's detailed profile to check their account status. If the status indicates 'Locked for security review', the process should stop and be escalated. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Unlock the user's account. The status badge should change to 'Active', and failed login attempts should reset to 0. [Platform: `mock` | Tool Call: `l1_testing_platform_api.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
