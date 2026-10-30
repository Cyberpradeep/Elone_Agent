---
type: Playbook
sop_id: SOP-PROXY-008
title: Enterprise Proxy Configuration Override
platform: system
category: network
target_os: windows
description: Automated workflow to configure WinHTTP proxy settings using a PAC URL
  and verify connectivity to an internal portal. Addresses reconfiguring PAC proxy
  routing for corporate endpoints.
confidence_score: 0.95
confidence_level: High
confidence_reason: Core proxy configuration and verification steps are fully automated.
  Preconditions and escalation criteria are noted as manual.
is_executable: true
unexecutable_reason: null
automation_status: partially_automated
required_entities:
- pac_url
- portal_url
trigger_words:
- proxy
- pac
- winhttp
- autoconfig
- netsh
steps:
- step_number: 1
  sop_step_description: Verify DNS resolution for the PAC file host to ensure the
    autoconfig URL is reachable.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: try { $pacHost = ([uri]'{{entities.pac_url}}').Host; Resolve-DnsName -Name
    $pacHost -ErrorAction Stop; Write-Host 'PAC host resolved successfully.' } catch
    { Write-Host 'PAC host DNS resolution failed.' }
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'PAC host resolved successfully.', set variables.pac_host_resolved
    = true, else set variables.pac_host_resolved = false
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: Check existing WinHTTP proxy settings to understand the current
    configuration.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: netsh winhttp show proxy
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Direct access (no proxy server).', set variables.proxy_not_set
    = true, else set variables.proxy_not_set = false
  execute_if: variables.pac_host_resolved == true
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Set the corporate proxy autoconfig URL using the provided
    PAC file.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: netsh winhttp set proxy autoconfigurl="{{entities.pac_url}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.pac_host_resolved == true
  timeout_seconds: 30
  shell: powershell
- step_number: 4
  sop_step_description: Test connectivity to the internal gateway portal to verify
    the new proxy configuration.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: 'try { $response = Invoke-WebRequest -Uri ''{{entities.portal_url}}'' -UseBasicParsing
    -ErrorAction Stop; Write-Host ''Status Code: '' + $response.StatusCode } catch
    { Write-Host ''Connection failed or error occurred.'' }'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: 'If stdout contains ''Status Code: 200'', set variables.portal_reachable
    = true. If stdout contains ''Status Code: 407'', set variables.proxy_auth_required
    = true. Else set variables.portal_reachable = false'
  execute_if: variables.pac_host_resolved == true
  timeout_seconds: 60
  shell: powershell
source_action_coverage:
- source_action: Workstation is joined to corp.internal Active Directory domain.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition check that is typically handled by system management or assumed.
- source_action: Active VPN tunnel is disconnected before executing PAC file change.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition that requires manual verification or a more complex VPN management
    integration.
- source_action: Administrative rights granted via temporary elevation token.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Precondition for execution, not an automated step within the playbook.
- source_action: Check existing WinHTTP proxy settings using netsh winhttp show proxy.
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Diagnostic command to inspect current proxy configuration.
- source_action: Set corporate proxy autoconfig URL using netsh winhttp set proxy
    autoconfigurl=http://pac.corp.internal/wpad.dat.
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: Corrective command to apply the new PAC URL.
- source_action: Test connectivity to internal gateway portal using Invoke-WebRequest
    -Uri https://portal.corp.internal.
  coverage: command_covered
  step_number: 4
  tool: null
  condition: null
  reason: Verification command to confirm proxy functionality.
- source_action: If proxy returns HTTP 407 Proxy Authentication Required, escalate
    immediately to Perimeter Security.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Escalation criteria based on command output, but the escalation itself is
    a human action.
- source_action: If WPAD autoconfig DNS record does not resolve, escalate to Core
    DNS Team.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Escalation criteria based on command output, but the escalation itself is
    a human action. DNS resolution check is automated in step 1.
document_metadata: {}
validation_confidence_score: 0.95
validation_confidence_level: High
validation_confidence_reason: The converted OKF steps accurately map to the executable
  actions in the raw SOP. The addition of a DNS resolution check (Step 1) is a valid
  diagnostic enhancement that supports the escalation criteria mentioned in the SOP.
  All commands are valid PowerShell/CLI strings, and no malicious or hallucinated
  actions were detected. Preconditions and manual escalations are correctly omitted
  as per the coverage ledger.
injection_detected: false
injection_reasoning: null
integrity_version: v2
integrity_hmac_sha256: 12997b89d6175700e167b7803f8c54888b0a6273be6fcfb5506c3a63870d4594
---

# Enterprise Proxy Configuration Override Playbook

## Overview
Automated workflow to configure WinHTTP proxy settings using a PAC URL and verify connectivity to an internal portal. Addresses reconfiguring PAC proxy routing for corporate endpoints.

## Execution Steps
- **Step 1**: Verify DNS resolution for the PAC file host to ensure the autoconfig URL is reachable. (`try { $pacHost = ([uri]'{{entities.pac_url}}').Host; Resolve-DnsName -Name $pacHost -ErrorAction Stop; Write-Host 'PAC host resolved successfully.' } catch { Write-Host 'PAC host DNS resolution failed.' }`)
- **Step 2**: Check existing WinHTTP proxy settings to understand the current configuration. (`netsh winhttp show proxy`)
- **Step 3**: Set the corporate proxy autoconfig URL using the provided PAC file. (`netsh winhttp set proxy autoconfigurl="{{entities.pac_url}}"`)
- **Step 4**: Test connectivity to the internal gateway portal to verify the new proxy configuration. (`try { $response = Invoke-WebRequest -Uri '{{entities.portal_url}}' -UseBasicParsing -ErrorAction Stop; Write-Host 'Status Code: ' + $response.StatusCode } catch { Write-Host 'Connection failed or error occurred.' }`)
