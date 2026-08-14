---
type: Playbook
sop_id: SOP-account-unlock-procedure-001
title: Account Unlock Procedure
category: logins
target_os: windows
description: Automated procedure to search for a locked user account by email, unlock
  it if locked, verify the unlock, and notify the user via email.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- unlock
- account
- locked
- login
steps:
- step_number: 1
  sop_step_description: Search for the user account using the customer's email address
    in the support platform
  step_type: tool_call
  platform: auth0
  provider: auth0_user_management
  function_name: search_user
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Check if the account status is locked. If not locked, skip
    unlock steps
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
  sop_step_description: Unlock the user account using the admin unlock function
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
  execute_if: variables.account_locked == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Verify the unlock was successful by checking account status
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
  execute_if: variables.unlock_success == 'true'
  timeout_seconds: 30
- step_number: 5
  sop_step_description: Send confirmation email to the customer notifying them their
    account is unlocked
  step_type: tool_call
  platform: system
  provider: system_operations
  function_name: send_email
  comm_inputs:
    to_email: '{{entities.email}}'
    subject: Your Account Has Been Unlocked
    body: Your account has been successfully unlocked. You can now log in again. If
      you continue to experience issues, please contact support.
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.unlock_verified == 'true'
  timeout_seconds: 30
---

# Account Unlock Procedure Playbook

## Overview
Automated procedure to search for a locked user account by email, unlock it if locked, verify the unlock, and notify the user via email.

## Execution Steps
- **Step 1**: Search for the user account using the customer's email address in the support platform [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
- **Step 2**: Check if the account status is locked. If not locked, skip unlock steps [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Unlock the user account using the admin unlock function [Platform: `mock` | Tool Call: `l1_testing_platform_api.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
- **Step 4**: Verify the unlock was successful by checking account status [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 5**: Send confirmation email to the customer notifying them their account is unlocked [Platform: `system` | Tool Call: `system_operations.send_email({"to_email": "{{entities.email}}", "subject": "Your Account Has Been Unlocked", "body": "Your account has been successfully unlocked. You can now log in again. If you continue to experience issues, please contact support."})`]
