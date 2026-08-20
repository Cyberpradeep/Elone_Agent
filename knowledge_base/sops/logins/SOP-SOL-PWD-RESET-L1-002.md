---
type: Playbook
sop_id: SOP-SOL-PWD-RESET-L1-002
title: Reset a Locked-Out User's Password via CoreID Admin Console
platform: solandra
category: logins
target_os: null
description: This playbook automates the L1 escalation procedure for resetting a locked-out
  user's password in the CoreID Admin Console. It includes steps for user lookup,
  identity verification, temporary password generation, and ticket resolution with
  audit logging.
confidence_score: 0.95
confidence_level: High
confidence_reason: All actions in the raw SOP mapped directly to registered Solandra
  platform tools with complete parameter schemas and high procedural fidelity. No
  unwritten actions were added.
required_entities:
- employee_id
- manager_name
- ticket_id
trigger_words:
- solandra
- unlock
- password reset
- locked account
- CoreID
- admin console
steps:
- step_number: 1
  sop_step_description: Confirm the ticket category and extract the requester's employee
    ID and manager name.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{entities.employee_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Confirm the user account is locked before proceeding.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{entities.employee_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_locked == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Verify the caller's identity using at least 2 of 4 identity
    items (employee ID, manager name, department, last 4 digits of phone).
  step_type: tool_call
  platform: solandra
  function_name: verify_caller_identity
  comm_inputs:
    user_id: '{{variables.employee_id}}'
    employee_id: '{{entities.employee_id}}'
    manager_name: '{{entities.manager_name}}'
    department: '{{entities.department}}'
    phone_last4: '{{entities.phone_last4}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_locked == 'true'
  timeout_seconds: 90
- step_number: 4
  sop_step_description: Generate a temporary password for the locked user and enable
    force change at next sign-in.
  step_type: tool_call
  platform: solandra
  function_name: generate_temporary_password
  comm_inputs:
    user_id: '{{variables.employee_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.verified == 'true'
  timeout_seconds: 30
- step_number: 5
  sop_step_description: Log the resolution audit note and set the ticket to Resolved.
  step_type: tool_call
  platform: solandra
  function_name: resolve_ticket
  comm_inputs:
    ticket_id: '{{entities.ticket_id}}'
    resolution_note: Identity verified (2 of 4 checks). Temporary password issued
      via CoreID. Force-change-at-next-sign-in enabled. No OTP sent - admin-mediated
      reset per policy.
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.force_change_enabled == 'true'
  timeout_seconds: 30
---

# Reset a Locked-Out User's Password via CoreID Admin Console Playbook

## Overview
This playbook automates the L1 escalation procedure for resetting a locked-out user's password in the CoreID Admin Console. It includes steps for user lookup, identity verification, temporary password generation, and ticket resolution with audit logging.

## Execution Steps
- **Step 1**: Confirm the ticket category and extract the requester's employee ID and manager name. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{entities.employee_id}}"})`]
- **Step 2**: Confirm the user account is locked before proceeding. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{entities.employee_id}}"})`]
- **Step 3**: Verify the caller's identity using at least 2 of 4 identity items (employee ID, manager name, department, last 4 digits of phone). [Platform: `solandra` | Tool Call: `solandra.verify_caller_identity({"user_id": "{{variables.employee_id}}", "employee_id": "{{entities.employee_id}}", "manager_name": "{{entities.manager_name}}", "department": "{{entities.department}}", "phone_last4": "{{entities.phone_last4}}"})`]
- **Step 4**: Generate a temporary password for the locked user and enable force change at next sign-in. [Platform: `solandra` | Tool Call: `solandra.generate_temporary_password({"user_id": "{{variables.employee_id}}"})`]
- **Step 5**: Log the resolution audit note and set the ticket to Resolved. [Platform: `solandra` | Tool Call: `solandra.resolve_ticket({"ticket_id": "{{entities.ticket_id}}", "resolution_note": "Identity verified (2 of 4 checks). Temporary password issued via CoreID. Force-change-at-next-sign-in enabled. No OTP sent - admin-mediated reset per policy."})`]
