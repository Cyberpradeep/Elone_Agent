---
type: Playbook
sop_id: SOP-SOC-016
title: Phishing Incident Host Isolation & Perimeter Domain Block
platform: system
category: security
target_os: windows
description: Automated playbook for rapid containment of compromised endpoints involved
  in phishing incidents, including host isolation, perimeter domain blocking, user
  session revocation, and DNS cache flushing. This playbook orchestrates actions from
  a Windows PowerShell environment, targeting both Windows endpoints and Linux-based
  network devices via SSH.
confidence_score: 0.95
confidence_level: High
confidence_reason: All core steps mapped to executable commands. External SSH commands
  assume pre-configured access and are executed from PowerShell. Variable linkage
  is explicit.
is_executable: true
unexecutable_reason: null
automation_status: partially_automated
required_entities:
- hostname
- malicious_domain
- target_user_id
trigger_words:
- phishing
- containment
- isolation
- firewall
- azuread
- dns
- soc
steps:
- step_number: 1
  sop_step_description: Query Falcon sensor API to retrieve the target host's device
    identifier.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: powershell -Command "Get-FalconHost -Filter \"hostname:'{{entities.hostname}}'\"
    | Select-Object -ExpandProperty device_id"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: Extract the first line of stdout as variables.device_id. If stdout
    is empty or contains an error, set variables.device_id = null.
  execute_if: null
  timeout_seconds: 60
  shell: powershell
- step_number: 2
  sop_step_description: Execute immediate network containment on the compromised endpoint
    via Falcon.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: powershell -Command "Invoke-FalconHostAction -Name 'contain' -Id '{{variables.device_id}}'"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Action completed successfully' or similar
    success message, set variables.host_contained = true, else set variables.host_contained
    = false.
  execute_if: variables.device_id != null
  timeout_seconds: 120
  shell: powershell
- step_number: 3
  sop_step_description: Push the malicious phishing domain indicator to the perimeter
    firewall blacklist.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: ssh soc-admin@firewall.corp.internal "configure; set security address-book
    Malicious_Domains address {{entities.malicious_domain}}; commit"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'commit complete', set variables.domain_blocked
    = true, else set variables.domain_blocked = false.
  execute_if: variables.device_id != null
  timeout_seconds: 90
  shell: powershell
- step_number: 4
  sop_step_description: Revoke all active enterprise authentication sessions and refresh
    tokens for the compromised user.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: powershell -Command "Revoke-AzureADUserAllRefreshToken -ObjectId '{{entities.target_user_id}}'"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.user_sessions_revoked = true,
    else set variables.user_sessions_revoked = false.
  execute_if: variables.device_id != null
  timeout_seconds: 60
  shell: powershell
- step_number: 5
  sop_step_description: Flush the edge DNS resolver cache to prevent further resolution
    of the malicious domain.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: ssh soc-admin@dns-gw.corp.internal "sudo systemctl restart unbound"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.dns_cache_flushed = true, else
    set variables.dns_cache_flushed = false.
  execute_if: variables.device_id != null
  timeout_seconds: 60
  shell: powershell
source_action_coverage:
- source_action: Phishing alert verified by email gateway sandbox analysis.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition requiring human verification, not an automated step.
- source_action: Operator holds SOC Tier 2 Analyst clearance with SSH keys configured
    on bastion.corp.internal.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition related to operator access and environment setup, not an automated
    step.
- source_action: Target endpoint hostname identified in EDR sensor telemetry.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition for providing the 'hostname' input, not an automated step within
    the playbook.
- source_action: Query Falcon sensor API to retrieve target host device identifier
    using powershell -Command "Get-FalconHost -Filter \"hostname:'endpoint-win-10'\"
    | Select-Object -ExpandProperty device_id".
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: PowerShell command to retrieve device ID from Falcon API.
- source_action: Execute immediate network containment on the compromised endpoint
    using powershell -Command "Invoke-FalconHostAction -Name 'contain' -Id $DEVICE_ID".
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: PowerShell command to initiate host containment via Falcon API.
- source_action: Push malicious phishing domain indicator to perimeter firewall blacklist
    using ssh soc-admin@firewall.corp.internal "configure; set security address-book
    Malicious_Domains address phishing-threat.com; commit".
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: SSH command executed from PowerShell to update firewall blacklist.
- source_action: Revoke all active enterprise authentication sessions and refresh
    tokens using powershell -Command "Revoke-AzureADUserAllRefreshToken -ObjectId
    $TARGET_USER_ID".
  coverage: command_covered
  step_number: 4
  tool: null
  condition: null
  reason: PowerShell command to revoke Azure AD user sessions.
- source_action: Flush edge DNS resolver cache to prevent further resolution of malicious
    domain using ssh soc-admin@dns-gw.corp.internal "sudo systemctl restart unbound".
  coverage: command_covered
  step_number: 5
  tool: null
  condition: null
  reason: SSH command executed from PowerShell to restart DNS resolver service.
- source_action: If EDR containment fails due to sensor heartbeat timeout, immediately
    disable the switch port on switch-core-01.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Escalation criteria describing a manual action or trigger for a separate
    playbook, not a direct command within this playbook.
- source_action: If lateral movement or Mimikatz execution is detected in memory telemetry,
    trigger Major Incident Severity 1.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Escalation criteria describing a manual action, not an automated step.
document_metadata: {}
validation_confidence_score: 1.0
validation_confidence_level: High
validation_confidence_reason: All executable steps from the raw SOP are accurately
  converted to OKF commands with correct parameterization and variable substitution.
  Manual/precondition/escalation steps are correctly identified as 'manual_ui_omitted'
  and are not present in the executable steps. No hallucinated commands or malicious
  injections were detected. All command steps are well-formed and executable within
  their declared shell.
injection_detected: false
injection_reasoning: null
integrity_version: v2
integrity_hmac_sha256: 084705b9418fc8618e266c969824ed879648f85d22f833ca24ee6cba59a7a0c4
---

# Phishing Incident Host Isolation & Perimeter Domain Block Playbook

## Overview
Automated playbook for rapid containment of compromised endpoints involved in phishing incidents, including host isolation, perimeter domain blocking, user session revocation, and DNS cache flushing. This playbook orchestrates actions from a Windows PowerShell environment, targeting both Windows endpoints and Linux-based network devices via SSH.

## Execution Steps
- **Step 1**: Query Falcon sensor API to retrieve the target host's device identifier. (`powershell -Command "Get-FalconHost -Filter \"hostname:'{{entities.hostname}}'\" | Select-Object -ExpandProperty device_id"`)
- **Step 2**: Execute immediate network containment on the compromised endpoint via Falcon. (`powershell -Command "Invoke-FalconHostAction -Name 'contain' -Id '{{variables.device_id}}'"`)
- **Step 3**: Push the malicious phishing domain indicator to the perimeter firewall blacklist. (`ssh soc-admin@firewall.corp.internal "configure; set security address-book Malicious_Domains address {{entities.malicious_domain}}; commit"`)
- **Step 4**: Revoke all active enterprise authentication sessions and refresh tokens for the compromised user. (`powershell -Command "Revoke-AzureADUserAllRefreshToken -ObjectId '{{entities.target_user_id}}'"`)
- **Step 5**: Flush the edge DNS resolver cache to prevent further resolution of the malicious domain. (`ssh soc-admin@dns-gw.corp.internal "sudo systemctl restart unbound"`)
