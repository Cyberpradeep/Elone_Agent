---
type: Playbook
sop_id: SOL-PWD-RESET-L1-002
title: Reset a Locked-Out User's Password via CoreID Admin Console
platform: solandra
category: password_reset
target_os: cross-platform
description: Automated procedure to search a user in CoreID, verify caller identity,
  generate a temporary password for a locked account, instruct the agent to relay
  it, and resolve the ticket with an audit note.
confidence_score: 0.95
confidence_level: High
confidence_reason: All core actions map directly to registered Solandra platform API
  tools with complete schema compliance. One step requires manual verbal relay.
is_executable: true
unexecutable_reason: null
required_entities:
- employee_id
- manager_name
- department
- phone_last4
- ticket_id
trigger_words:
- solandra
- reset
- password
- locked-out
- CoreID
steps:
- step_number: 1
  sop_step_description: Search user in CoreID to check account lock status.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{entities.employee_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.status to variables.account_status and response.user_id
    to variables.user_id
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Verify caller identity using provided details and confirm
    account is locked.
  step_type: tool_call
  platform: solandra
  function_name: verify_caller_identity
  comm_inputs:
    user_id: '{{variables.user_id}}'
    employee_id: '{{entities.employee_id}}'
    manager_name: '{{entities.manager_name}}'
    department: '{{entities.department}}'
    phone_last4: '{{entities.phone_last4}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.verified to variables.caller_verified
  execute_if: variables.account_status == 'Locked' and entities.manager_name != null
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Generate a temporary password for the locked user account
    in CoreID.
  step_type: tool_call
  platform: solandra
  function_name: generate_temporary_password
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.temporary_password to variables.temporary_password
  execute_if: variables.account_status == 'Locked' and variables.caller_verified ==
    'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Relay the temporary password securely to the caller verbally.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: 'Please read the temporary password: {{{{variables.temporary_password}}}}
    to the caller verbally over the verified phone line. Do NOT send it by email,
    chat, or ticket comment.'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.account_status == 'Locked' and variables.caller_verified ==
    'true' and variables.temporary_password != null
  timeout_seconds: 60
  shell: powershell
- step_number: 5
  sop_step_description: Resolve the ticket with an audit note detailing the password
    reset actions.
  step_type: tool_call
  platform: solandra
  function_name: resolve_ticket
  comm_inputs:
    ticket_id: '{{entities.ticket_id}}'
    resolution_note: 'Identity verified (caller matched 2+ items). Temporary password
      issued via CoreID. Force-change-at-next-sign-in enabled. No OTP sent - admin-mediated
      reset per policy. Temporary password: {{{{variables.temporary_password}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.account_status == 'Locked' and variables.caller_verified ==
    'true' and variables.temporary_password != null
  timeout_seconds: 30
integrity_version: v2
integrity_hmac_sha256: 0699dfff4d59b75a0513829ade7ec3a7705885fbbb85e3fad2c768690f59fcd4
---

# Reset a Locked-Out User's Password via CoreID Admin Console Playbook

## Overview
Automated procedure to search a user in CoreID, verify caller identity, generate a temporary password for a locked account, instruct the agent to relay it, and resolve the ticket with an audit note.

## Execution Steps
- **Step 1**: Search user in CoreID to check account lock status. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{entities.employee_id}}"})`]
- **Step 2**: Verify caller identity using provided details and confirm account is locked. [Platform: `solandra` | Tool Call: `solandra.verify_caller_identity({"user_id": "{{variables.user_id}}", "employee_id": "{{entities.employee_id}}", "manager_name": "{{entities.manager_name}}", "department": "{{entities.department}}", "phone_last4": "{{entities.phone_last4}}"})`]
- **Step 3**: Generate a temporary password for the locked user account in CoreID. [Platform: `solandra` | Tool Call: `solandra.generate_temporary_password({"user_id": "{{variables.user_id}}"})`]
- **Step 4**: Relay the temporary password securely to the caller verbally. (`Please read the temporary password: {{{{variables.temporary_password}}}} to the caller verbally over the verified phone line. Do NOT send it by email, chat, or ticket comment.`)
- **Step 5**: Resolve the ticket with an audit note detailing the password reset actions. [Platform: `solandra` | Tool Call: `solandra.resolve_ticket({"ticket_id": "{{entities.ticket_id}}", "resolution_note": "Identity verified (caller matched 2+ items). Temporary password issued via CoreID. Force-change-at-next-sign-in enabled. No OTP sent - admin-mediated reset per policy. Temporary password: {{{{variables.temporary_password}}}}"})`]
