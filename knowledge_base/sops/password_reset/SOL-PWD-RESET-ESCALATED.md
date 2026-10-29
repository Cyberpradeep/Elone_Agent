---
type: Playbook
sop_id: SOL-PWD-RESET-ESCALATED
title: Reset a Locked-Out User's Password via CoreID Admin Console
platform: solandra
category: password_reset
target_os: cross-platform
description: 'L1 escalation runbook for Solandra Corp: an authorized agent with the
  CoreID Password Reset Admin role locates a locked user, verifies caller identity
  via the 2-of-4 checklist, generates a temporary password with force-change-at-next-sign-in
  enabled, and resolves the ticket with an audit note. The temporary password is relayed
  verbally over the verified phone line and is never sent by email, chat, or ticket
  comment.'
confidence_score: 0.95
confidence_level: High
confidence_reason: All CoreID Admin Console and ticketing actions map directly to
  registered solandra platform functions (search_user, verify_caller_identity, generate_temporary_password,
  resolve_ticket) with complete schema compliance. Ticket review and verbal password
  relay are human/UI actions with no registered tool and are intentionally excluded
  from executable steps.
is_executable: true
unexecutable_reason: null
automation_status: partially_automated
required_entities:
- employee_id
- manager_name
- department
- phone_last4
- ticket_id
trigger_words:
- solandra
- password reset
- locked
- coreid
- temporary password
- escalated
- identity verification
- force change
steps:
- step_number: 1
  sop_step_description: Search the CoreID user directory by employee ID to locate
    the account and confirm its lock status.
  step_type: tool_call
  platform: solandra
  function_name: search_user
  comm_inputs:
    employee_id: '{{entities.employee_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.found to variables.user_found, response.user_id
    to variables.user_id, response.status to variables.account_status, response.manager_name
    to variables.manager_name, and response.department to variables.department
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: 'Verify the caller''s identity against the CoreID checklist
    (minimum 2 of 4 items: employee ID, manager name, department, phone last 4). No
    one-time code is sent.'
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
  parse_instruction: Extract response.verified to variables.identity_verified, response.matched_count
    to variables.matched_count, and response.matched_items to variables.matched_items
  execute_if: variables.user_found == 'true' && variables.account_status == 'Locked'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Generate a temporary password for the locked user with force-change-at-next-sign-in
    left enabled.
  step_type: tool_call
  platform: solandra
  function_name: generate_temporary_password
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.temporary_password to variables.temporary_password,
    response.force_change_at_next_sign_in to variables.force_change_enabled, and response.status
    to variables.password_status
  execute_if: variables.account_status == 'Locked' && variables.identity_verified
    == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Log the resolution audit note (identity checks matched, temporary
    password issued, force-change enabled) and set the ticket to Resolved.
  step_type: tool_call
  platform: solandra
  function_name: resolve_ticket
  comm_inputs:
    ticket_id: '{{entities.ticket_id}}'
    resolution_note: 'Admin-mediated password reset completed. Caller identity verified
      ({{variables.matched_count}} of 4 checks matched: {{variables.matched_items}}).
      Temporary password issued via CoreID. Force-change-at-next-sign-in: enabled.
      No OTP sent - admin-mediated reset per policy. Temporary password relayed verbally
      over verified phone line.'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract response.status to variables.ticket_status and response.audit_logged
    to variables.audit_logged
  execute_if: variables.password_status == 'success'
  timeout_seconds: 30
source_action_coverage:
- source_action: 'Step 1: Review ticket, confirm category is ''Password Reset - Escalated'',
    and note employee ID and manager name (do not proceed if manager name missing)'
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: This is a human ticket-reading/inspection action in the ticketing system
    with no registered tool that reads or validates ticket category. It is a precondition
    gate handled by the agent before automation begins.
- source_action: 'Step 2: Search CoreID Users by employee ID and confirm the account
    status badge shows Locked'
  coverage: tool_covered
  step_number: 1
  tool: solandra.search_user
  condition: null
  reason: Registered search_user returns the user's status (e.g. 'Locked'), covering
    the SOP outcome of locating the user and confirming lock status.
- source_action: 'Step 3: Verify caller identity against the checklist (minimum 2
    of 4: employee ID, manager name, department, phone last 4); do NOT send a one-time
    code'
  coverage: tool_covered
  step_number: 2
  tool: solandra.verify_caller_identity
  condition: null
  reason: Registered verify_caller_identity performs the 2-of-4 checklist verification
    and returns matched_count, covering the SOP outcome without sending any OTP.
- source_action: 'Step 4: Generate Temporary Password with ''Force change at next
    sign-in'' left checked'
  coverage: tool_covered
  step_number: 3
  tool: solandra.generate_temporary_password
  condition: null
  reason: Registered generate_temporary_password issues the temporary password and
    keeps force_change_at_next_sign_in enabled, matching the SOP requirement.
- source_action: 'Step 5: Relay the temporary password verbally over the verified
    phone line (never by email, chat, or ticket comment)'
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: This is a human voice-channel action. The SOP explicitly forbids sending
    the password by email/chat/ticket, so no email or messaging tool is invoked. No
    registered tool performs a secure verbal relay.
- source_action: 'Step 6: Log the resolution audit note (identity checks matched,
    temporary password issued, force-change enabled) and set the ticket to Resolved'
  coverage: tool_covered
  step_number: 4
  tool: solandra.resolve_ticket
  condition: null
  reason: Registered resolve_ticket writes the resolution audit note and sets ticket
    status to Resolved, satisfying the audit trail requirement.
validation_confidence_score: 1.0
validation_confidence_level: High
validation_confidence_reason: The OKF steps accurately map to the executable portions
  of the SOP. Manual steps (ticket review, verbal relay) are correctly omitted per
  the coverage ledger and exemption rules. Tool parameters and logic gates align with
  the SOP requirements.
injection_detected: false
injection_reasoning: No prompt injection or malicious commands detected. All steps
  correspond to legitimate administrative actions defined in the SOP.
integrity_version: v2
integrity_hmac_sha256: 0a411ad574538d33330ddf31fb73e91c1d90162bf1cf3a6bd4c42c890d0bfe9d
---

# Reset a Locked-Out User's Password via CoreID Admin Console Playbook

## Overview
L1 escalation runbook for Solandra Corp: an authorized agent with the CoreID Password Reset Admin role locates a locked user, verifies caller identity via the 2-of-4 checklist, generates a temporary password with force-change-at-next-sign-in enabled, and resolves the ticket with an audit note. The temporary password is relayed verbally over the verified phone line and is never sent by email, chat, or ticket comment.

## Execution Steps
- **Step 1**: Search the CoreID user directory by employee ID to locate the account and confirm its lock status. [Platform: `solandra` | Tool Call: `solandra.search_user({"employee_id": "{{entities.employee_id}}"})`]
- **Step 2**: Verify the caller's identity against the CoreID checklist (minimum 2 of 4 items: employee ID, manager name, department, phone last 4). No one-time code is sent. [Platform: `solandra` | Tool Call: `solandra.verify_caller_identity({"user_id": "{{variables.user_id}}", "employee_id": "{{entities.employee_id}}", "manager_name": "{{entities.manager_name}}", "department": "{{entities.department}}", "phone_last4": "{{entities.phone_last4}}"})`]
- **Step 3**: Generate a temporary password for the locked user with force-change-at-next-sign-in left enabled. [Platform: `solandra` | Tool Call: `solandra.generate_temporary_password({"user_id": "{{variables.user_id}}"})`]
- **Step 4**: Log the resolution audit note (identity checks matched, temporary password issued, force-change enabled) and set the ticket to Resolved. [Platform: `solandra` | Tool Call: `solandra.resolve_ticket({"ticket_id": "{{entities.ticket_id}}", "resolution_note": "Admin-mediated password reset completed. Caller identity verified ({{variables.matched_count}} of 4 checks matched: {{variables.matched_items}}). Temporary password issued via CoreID. Force-change-at-next-sign-in: enabled. No OTP sent - admin-mediated reset per policy. Temporary password relayed verbally over verified phone line."})`]
