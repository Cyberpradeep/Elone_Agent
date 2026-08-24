---
type: Playbook
sop_id: SOL-PWD-RESET-L1-002
title: Reset a Locked-Out User's Password via CoreID Admin Console
platform: solandra
category: logins
target_os: windows
description: When a user's self-service password reset fails or the user has no working
  verification channel, an authorized L1 agent with the Password Reset Admin role
  in CoreID resets the password directly from the admin console, verifies caller identity,
  issues a temporary password, and resolves the ticket.
confidence_score: 0.95
confidence_level: High
confidence_reason: All automated actions mapped directly to registered `solandra`
  platform tools with complete parameter schemas. Manual steps were correctly omitted,
  and dynamic variables are used for high procedural fidelity.
required_entities:
- employee_id
- manager_name
- department
- phone_last4
- ticket_id
trigger_words:
- solandra
- reset password
- locked out
- coreid
- password reset escalated
steps:
- step_number: 1
  sop_step_description: User located and lock confirmed
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{{{entities.employee_id}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Caller identity verified
  step_type: tool_call
  platform: solandra
  function_name: verify_caller_identity
  comm_inputs:
    user_id: '{{{{variables.user_details.user_id}}}}'
    employee_id: '{{{{entities.employee_id}}}}'
    manager_name: '{{{{entities.manager_name}}}}'
    department: '{{{{entities.department}}}}'
    phone_last4: '{{{{entities.phone_last4}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_details.status == 'Locked' and variables.user_details.found
    == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Temporary password issued
  step_type: tool_call
  platform: solandra
  function_name: generate_temporary_password
  comm_inputs:
    user_id: '{{{{variables.user_details.user_id}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.identity_verification_result.verified == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Ticket resolved with audit note
  step_type: tool_call
  platform: solandra
  function_name: resolve_ticket
  comm_inputs:
    ticket_id: '{{{{entities.ticket_id}}}}'
    resolution_note: 'Identity verified ({{{{variables.identity_verification_result.matched_count}}}}
      of 4 checks). Temporary password issued via CoreID. Force-change-at-next-sign-in
      enabled. No OTP sent - admin-mediated reset per policy. Temporary password:
      {{{{variables.password_reset_result.temporary_password}}}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.password_reset_result.status == 'success'
  timeout_seconds: 30
---

# Reset a Locked-Out User's Password via CoreID Admin Console Playbook

## Overview
When a user's self-service password reset fails or the user has no working verification channel, an authorized L1 agent with the Password Reset Admin role in CoreID resets the password directly from the admin console, verifies caller identity, issues a temporary password, and resolves the ticket.

## Execution Steps
- **Step 1**: User located and lock confirmed [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{{{entities.employee_id}}}}"})`]
- **Step 2**: Caller identity verified [Platform: `solandra` | Tool Call: `solandra.verify_caller_identity({"user_id": "{{{{variables.user_details.user_id}}}}", "employee_id": "{{{{entities.employee_id}}}}", "manager_name": "{{{{entities.manager_name}}}}", "department": "{{{{entities.department}}}}", "phone_last4": "{{{{entities.phone_last4}}}}"})`]
- **Step 3**: Temporary password issued [Platform: `solandra` | Tool Call: `solandra.generate_temporary_password({"user_id": "{{{{variables.user_details.user_id}}}}"})`]
- **Step 4**: Ticket resolved with audit note [Platform: `solandra` | Tool Call: `solandra.resolve_ticket({"ticket_id": "{{{{entities.ticket_id}}}}", "resolution_note": "Identity verified ({{{{variables.identity_verification_result.matched_count}}}} of 4 checks). Temporary password issued via CoreID. Force-change-at-next-sign-in enabled. No OTP sent - admin-mediated reset per policy. Temporary password: {{{{variables.password_reset_result.temporary_password}}}}"})`]
