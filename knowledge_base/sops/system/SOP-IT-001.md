---
type: Playbook
sop_id: SOP-IT-001
title: Active Directory User Password Reset
platform: system
category: system
target_os: windows
description: Automated workflow to locate an Active Directory user, reset their password,
  and enforce a password change at next logon.
confidence_score: 0.95
confidence_level: High
confidence_reason: Core AD operations are fully automatable via PowerShell. Human
  verification and notification steps are correctly omitted from execution but tracked
  in coverage.
is_executable: true
unexecutable_reason: null
automation_status: partially_automated
required_entities:
- username
- temporary_password
trigger_words:
- password reset
- active directory
- ad user
- credential reset
steps:
- step_number: 1
  sop_step_description: Locate the user account in Active Directory to verify existence
    and retrieve object details.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Get-ADUser -Identity "{{entities.username}}" -Properties *
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If command succeeds and returns user object, set variables.user_found
    = true, else set variables.user_found = false
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: Reset the target account password to the specified temporary
    complex credentials.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: $securePass = ConvertTo-SecureString '{{entities.temporary_password}}'
    -AsPlainText -Force; Set-ADAccountPassword -Identity "{{entities.username}}" -Reset
    -NewPassword $securePass
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.password_reset = true, else
    set variables.password_reset = false
  execute_if: variables.user_found == true
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Flag the user account to require password change at next logon.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Set-ADUser -Identity "{{entities.username}}" -ChangePasswordAtLogon $true
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.change_flagged = true, else
    set variables.change_flagged = false
  execute_if: variables.password_reset == true
  timeout_seconds: 30
  shell: powershell
source_action_coverage:
- source_action: Open PowerShell terminal with elevated administrator privileges
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Environment setup instruction; assumed by execution context.
- source_action: Search and locate the user account in Active Directory using Get-ADUser
    cmdlet
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Diagnostic discovery step to verify user existence.
- source_action: Reset the target account password using Set-ADAccountPassword with
    temporary complex credentials
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Corrective action to reset password.
- source_action: Flag the user account to require password change at next logon using
    Set-ADUser -ChangePasswordAtLogon $true
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: Corrective action to enforce password change.
- source_action: Notify the employee securely via SMS or corporate one-time link
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Human/external communication step not automatable in this context.
document_metadata: {}
validation_confidence_score: 0.95
validation_confidence_level: High
validation_confidence_reason: The executable steps accurately reflect the core technical
  actions of the SOP. Omitted steps (PowerShell launch, SMS notification) are correctly
  classified as manual/UI or non-automatable in the ledger. Commands are syntactically
  valid PowerShell.
injection_detected: false
injection_reasoning: No prompt injection or malicious commands detected. All commands
  are standard Active Directory management cmdlets aligned with the SOP.
integrity_version: v2
integrity_hmac_sha256: a64add7bf1c6f4dcd54cb10868a2c3e7233754a917f547c3d8cd29d058a143ed
---

# Active Directory User Password Reset Playbook

## Overview
Automated workflow to locate an Active Directory user, reset their password, and enforce a password change at next logon.

## Execution Steps
- **Step 1**: Locate the user account in Active Directory to verify existence and retrieve object details. (`Get-ADUser -Identity "{{entities.username}}" -Properties *`)
- **Step 2**: Reset the target account password to the specified temporary complex credentials. (`$securePass = ConvertTo-SecureString '{{entities.temporary_password}}' -AsPlainText -Force; Set-ADAccountPassword -Identity "{{entities.username}}" -Reset -NewPassword $securePass`)
- **Step 3**: Flag the user account to require password change at next logon. (`Set-ADUser -Identity "{{entities.username}}" -ChangePasswordAtLogon $true`)
