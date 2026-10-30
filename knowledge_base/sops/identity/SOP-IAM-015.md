---
type: Playbook
sop_id: SOP-IAM-015
title: Identity Provider MFA Factor De-enrollment via Admin API CLI
platform: system
category: identity
target_os: windows
description: Automated workflow to identify user, list MFA factors, delete compromised
  factor, revoke sessions, and reset factors via Okta REST API using PowerShell.
confidence_score: 0.95
confidence_level: High
confidence_reason: All steps mapped to deterministic PowerShell Invoke-RestMethod
  commands with variable linkage for User ID and Factor ID. Escalation criteria handled
  via error parsing.
is_executable: true
unexecutable_reason: null
automation_status: fully_automated
required_entities:
- username
- factor_id
trigger_words:
- mfa
- okta
- de-enroll
- factor
- reset
- identity
steps:
- step_number: 1
  sop_step_description: Query directory user endpoint to obtain target employee unique
    identifier.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; $response
    = Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users?q={{entities.username}}"
    -Headers $headers -Method Get; $response[0].id
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If command succeeds and returns a non-empty string, set variables.user_id
    = <stdout>, else set variables.user_id = null and variables.api_error = true
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: List all currently registered authentication factors for target
    user.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod
    -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/factors"
    -Headers $headers -Method Get | ConvertTo-Json
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains JSON array, set variables.factors_list = <stdout>,
    else set variables.factors_list = null
  execute_if: variables.user_id != null
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Delete the specific compromised or lost mobile device factor.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod
    -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/factors/{{entities.factor_id}}"
    -Headers $headers -Method Delete
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0 or no exception thrown, set variables.factor_deleted
    = true, else set variables.factor_deleted = false
  execute_if: variables.user_id != null
  timeout_seconds: 30
  shell: powershell
- step_number: 4
  sop_step_description: Revoke all active user web and API bearer sessions immediately.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod
    -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/lifecycle/clear_sessions"
    -Headers $headers -Method Post
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0 or no exception thrown, set variables.sessions_cleared
    = true, else set variables.sessions_cleared = false
  execute_if: variables.user_id != null
  timeout_seconds: 30
  shell: powershell
- step_number: 5
  sop_step_description: Issue a temporary 24-hour factor re-enrollment activation
    token.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod
    -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/lifecycle/reset_factors"
    -Headers $headers -Method Post
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0 or no exception thrown, set variables.factors_reset
    = true, else set variables.factors_reset = false
  execute_if: variables.user_id != null
  timeout_seconds: 30
  shell: powershell
source_action_coverage:
- source_action: Query directory user endpoint to obtain target employee unique identifier
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Mapped to Invoke-RestMethod GET request to /api/v1/users.
- source_action: List all currently registered authentication factors for target user
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Mapped to Invoke-RestMethod GET request to /api/v1/users/{id}/factors.
- source_action: Delete the specific compromised or lost mobile device factor
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: Mapped to Invoke-RestMethod DELETE request to /api/v1/users/{id}/factors/{factor_id}.
- source_action: Revoke all active user web and API bearer sessions immediately
  coverage: command_covered
  step_number: 4
  tool: null
  condition: null
  reason: Mapped to Invoke-RestMethod POST request to /api/v1/users/{id}/lifecycle/clear_sessions.
- source_action: Issue a temporary 24-hour factor re-enrollment activation token
  coverage: command_covered
  step_number: 5
  tool: null
  condition: null
  reason: Mapped to Invoke-RestMethod POST request to /api/v1/users/{id}/lifecycle/reset_factors.
- source_action: If HTTP 403 Forbidden is returned, verify administrator RBAC permissions
    and session token expiration
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Human verification of RBAC and token expiration is not automatable in this
    context; error is captured in step 1 parse.
- source_action: If user account shows anomalous authentication attempts from external
    IP addresses, lock account and escalate to SOC
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Anomalous attempt detection and SOC escalation require human judgment and
    external system interaction not covered by this specific API flow.
document_metadata: {}
validation_confidence_score: 0.95
validation_confidence_level: High
validation_confidence_reason: The converted steps accurately map to the SOP's procedural
  steps using appropriate PowerShell commands. The escalation criteria are correctly
  identified as manual/human tasks and omitted from the executable playbook as per
  the coverage ledger.
injection_detected: false
injection_reasoning: No prompt injection or malicious commands detected. All steps
  correspond to legitimate API calls defined in the SOP.
integrity_version: v2
integrity_hmac_sha256: 563704a9428b499e9d386c96f8840955fea6709fdd9cbedd6546a363129198b8
---

# Identity Provider MFA Factor De-enrollment via Admin API CLI Playbook

## Overview
Automated workflow to identify user, list MFA factors, delete compromised factor, revoke sessions, and reset factors via Okta REST API using PowerShell.

## Execution Steps
- **Step 1**: Query directory user endpoint to obtain target employee unique identifier. (`$headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; $response = Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users?q={{entities.username}}" -Headers $headers -Method Get; $response[0].id`)
- **Step 2**: List all currently registered authentication factors for target user. (`$headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/factors" -Headers $headers -Method Get | ConvertTo-Json`)
- **Step 3**: Delete the specific compromised or lost mobile device factor. (`$headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/factors/{{entities.factor_id}}" -Headers $headers -Method Delete`)
- **Step 4**: Revoke all active user web and API bearer sessions immediately. (`$headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/lifecycle/clear_sessions" -Headers $headers -Method Post`)
- **Step 5**: Issue a temporary 24-hour factor re-enrollment activation token. (`$headers = @{ 'Authorization' = "SSWS $env:OKTA_API_TOKEN" }; Invoke-RestMethod -Uri "https://portal.corp.internal/api/v1/users/{{variables.user_id}}/lifecycle/reset_factors" -Headers $headers -Method Post`)
