---
type: Playbook
sop_id: SOP-Account-Unlock-Procedure-001
title: Account Unlock Procedure
platform: solandra
category: logins
target_os: windows
description: This playbook automates the process of searching for a user account,
  checking its lock status, attempting to unlock it (by generating a temporary password),
  verifying the unlock, and sending a confirmation email.
confidence_score: 0.75
confidence_level: Medium
confidence_reason: Some SOP actions required interpretation due to mismatches between
  the SOP's specified inputs (email for search) and the tool's required inputs (employee_id),
  and the absence of a direct 'unlock' function, necessitating the use of 'generate_temporary_password'
  as a proxy. However, all steps are mapped to available tools.
required_entities:
- email
trigger_words:
- solandra
- unlock
- account
- login
- locked
steps:
- step_number: 1
  sop_step_description: Search for the user account using the customer's email address
    in the support platform.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{{{entities.email}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.user_id to variables.user_id, and check response.status == 'Locked' (set variables.account_status = response.status)
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: If the account is locked, unlock the user account using the
    admin unlock function with the user_id.
  step_type: tool_call
  platform: solandra
  function_name: generate_temporary_password
  comm_inputs:
    user_id: '{{{{variables.user_id}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.temporary_password to variables.temporary_password
  execute_if: variables.account_status == 'Locked'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Verify the unlock was successful by checking the account status
    is now 'unlocked'.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{{{entities.email}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Verify response.status != 'Locked' and set variables.unlock_verified = true, else set variables.unlock_verified = false
  execute_if: variables.account_status == 'Locked'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Send a confirmation email to the customer notifying them that
    their account has been unlocked and they can try logging in again.
  step_type: tool_call
  platform: email
  function_name: send_email
  comm_inputs:
    to_email: '{{{{entities.email}}}}'
    subject: Account Unlocked
    body: Your account has been unlocked and you can try logging in again.
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.unlock_verified == true
  timeout_seconds: 30
---

# Account Unlock Procedure Playbook

## Overview
This playbook automates the process of searching for a user account, checking its lock status, attempting to unlock it (by generating a temporary password), verifying the unlock, and sending a confirmation email.

## Execution Steps
- **Step 1**: Search for the user account using the customer's email address in the support platform. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{{{entities.email}}}}"})`]
- **Step 2**: If the account is locked, unlock the user account using the admin unlock function with the user_id. [Platform: `solandra` | Tool Call: `solandra.generate_temporary_password({"user_id": "{{{{variables.user_id}}}}"})`]
- **Step 3**: Verify the unlock was successful by checking the account status is now 'unlocked'. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{{{entities.email}}}}"})`]
- **Step 4**: Send a confirmation email to the customer notifying them that their account has been unlocked and they can try logging in again. [Platform: `email` | Tool Call: `email.send_email({"to_email": "{{{{entities.email}}}}", "subject": "Account Unlocked", "body": "Your account has been unlocked and you can try logging in again."})`]
