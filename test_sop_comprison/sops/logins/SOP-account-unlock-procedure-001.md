---
type: Playbook
sop_id: SOP-account-unlock-procedure-001
title: Account Unlock Procedure
category: logins
target_os: windows
description: This playbook automates the procedure for unlocking a user account in
  the support platform. It searches for the user by email, checks if the account is
  locked, unlocks it if necessary, verifies the unlock, and sends a confirmation email
  to the user.
knowledge_base_ref: []
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
  sop_step_description: Search for the user account using the customer's email address
    in the support platform.
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
  sop_step_description: Check if the account status is 'locked'.
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
  sop_step_description: Inform the user that no action is needed if the account is
    not locked.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: Write-Host 'Account is not locked. No action is needed.'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.account_locked == 'false'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Unlock the user account using the admin unlock function with
    the user_id.
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
- step_number: 5
  sop_step_description: Verify the unlock was successful by checking the account status
    is now 'unlocked'.
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
- step_number: 6
  sop_step_description: Send a confirmation email to the customer notifying them that
    their account has been unlocked.
  step_type: tool_call
  platform: email
  provider: email_service
  function_name: send_email
  comm_inputs:
    to_email: '{{entities.email}}'
    subject: Your Account Has Been Unlocked
    body: 'Dear User,


      Your account has been successfully unlocked. You can now log in again.


      Best regards,

      Support Team'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.unlock_verified == 'true'
  timeout_seconds: 30
---

# Account Unlock Procedure Playbook

## Overview
This playbook automates the procedure for unlocking a user account in the support platform. It searches for the user by email, checks if the account is locked, unlocks it if necessary, verifies the unlock, and sends a confirmation email to the user.

## Execution Steps
- **Step 1**: Search for the user account using the customer's email address in the support platform. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Check if the account status is 'locked'. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Inform the user that no action is needed if the account is not locked. (`Write-Host 'Account is not locked. No action is needed.'`)
- **Step 4**: Unlock the user account using the admin unlock function with the user_id. [Platform: `mock` | Tool Call: `l1_testing_platform_api.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
- **Step 5**: Verify the unlock was successful by checking the account status is now 'unlocked'. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 6**: Send a confirmation email to the customer notifying them that their account has been unlocked. [Platform: `email` | Tool Call: `email_service.send_email({"to_email": "{{entities.email}}", "subject": "Your Account Has Been Unlocked", "body": "Dear User,\n\nYour account has been successfully unlocked. You can now log in again.\n\nBest regards,\nSupport Team"})`]
