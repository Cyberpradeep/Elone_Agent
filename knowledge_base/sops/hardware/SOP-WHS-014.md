---
type: Playbook
sop_id: SOP-WHS-014
title: Warehouse Barcode Scanner Terminal Soft Reset & Staging Recovery
platform: system
category: hardware
target_os: windows
description: Automated workflow to verify ADB connectivity, clear application cache,
  apply staging profile, verify configuration, and reboot Zebra TC52 scanners.
confidence_score: 0.95
confidence_level: High
confidence_reason: All steps mapped to deterministic ADB commands with explicit state
  gating and fallback handling for connectivity issues.
is_executable: true
unexecutable_reason: null
automation_status: fully_automated
required_entities:
- hostname
- application_package
- staging_script_path
trigger_words:
- zebra
- tc52
- adb
- scanner
- reset
- staging
- logcat
steps:
- step_number: 1
  sop_step_description: Verify ADB connectivity and device state before executing
    recovery commands.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: adb get-state
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'device', set variables.device_online = true,
    else set variables.device_online = false
  execute_if: null
  timeout_seconds: 15
  shell: powershell
- step_number: 2
  sop_step_description: Purge memory cache for the warehouse fulfillment scan application.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: adb shell pm clear "{{entities.application_package}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Success', set variables.cache_cleared = true,
    else set variables.cache_cleared = false
  execute_if: variables.device_online == true
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Broadcast StageNow automated staging intent profile to apply
    configuration.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: adb shell am broadcast -a com.symbol.stagenow.action.EXECUTE -e script_file
    "{{entities.staging_script_path}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Broadcast completed', set variables.profile_broadcast
    = true, else set variables.profile_broadcast = false
  execute_if: variables.device_online == true
  timeout_seconds: 30
  shell: powershell
- step_number: 4
  sop_step_description: Query device diagnostic logcat to confirm successful profile
    application.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: adb logcat -d -s StageNow | Select-String -Pattern 'Configuration\s+applied\s+successfully'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout is not empty, set variables.profile_applied = true,
    else set variables.profile_applied = false
  execute_if: variables.device_online == true
  timeout_seconds: 30
  shell: powershell
- step_number: 5
  sop_step_description: Soft reboot the mobile computer scanner to apply persistent
    runtime settings.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: adb reboot
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.device_online == true
  timeout_seconds: 60
  shell: powershell
source_action_coverage:
- source_action: Check USB dock communication and verify connected scanner state using
    adb get-state
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Deterministic ADB state check.
- source_action: Forcefully terminate and purge memory cache for the warehouse fulfillment
    scan app using adb shell pm clear
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Deterministic ADB package clear command.
- source_action: Broadcast the StageNow automated staging intent profile using adb
    shell am broadcast
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: Deterministic ADB broadcast command.
- source_action: Query device diagnostic logcat buffer to confirm successful profile
    application
  coverage: command_covered
  step_number: 4
  tool: null
  condition: null
  reason: Deterministic ADB logcat query with Select-String parsing.
- source_action: Soft reboot the mobile computer scanner to apply persistent runtime
    settings using adb reboot
  coverage: command_covered
  step_number: 5
  tool: null
  condition: null
  reason: Deterministic ADB reboot command.
- source_action: If adb get-state returns unauthorized or device offline, re-seat
    device in USB dock or replace staging cable
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Physical hardware intervention (re-seating/replacing cable) cannot be automated
    via CLI.
- source_action: If scan engine hardware fails to calibrate after reboot, mark scanner
    hardware defective and route to vendor RMA
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: Hardware defect assessment and RMA routing require human judgment and physical
    handling.
document_metadata: {}
validation_confidence_score: 0.95
validation_confidence_level: High
validation_confidence_reason: All executable steps from the SOP are accurately represented
  in the JSON. The use of placeholders for specific package names and file paths is
  appropriate for a generic playbook. The omission of physical hardware interventions
  is correctly handled as manual_ui_omitted. The commands are valid PowerShell/ADB
  syntax.
injection_detected: false
injection_reasoning: No prompt injection or malicious commands detected. All commands
  are standard ADB operations aligned with the SOP.
integrity_version: v2
integrity_hmac_sha256: b75b4ea53f363072a9b2a4172230f8e213a3120d8210f44bc0c3984589da308e
---

# Warehouse Barcode Scanner Terminal Soft Reset & Staging Recovery Playbook

## Overview
Automated workflow to verify ADB connectivity, clear application cache, apply staging profile, verify configuration, and reboot Zebra TC52 scanners.

## Execution Steps
- **Step 1**: Verify ADB connectivity and device state before executing recovery commands. (`adb get-state`)
- **Step 2**: Purge memory cache for the warehouse fulfillment scan application. (`adb shell pm clear "{{entities.application_package}}"`)
- **Step 3**: Broadcast StageNow automated staging intent profile to apply configuration. (`adb shell am broadcast -a com.symbol.stagenow.action.EXECUTE -e script_file "{{entities.staging_script_path}}"`)
- **Step 4**: Query device diagnostic logcat to confirm successful profile application. (`adb logcat -d -s StageNow | Select-String -Pattern 'Configuration\s+applied\s+successfully'`)
- **Step 5**: Soft reboot the mobile computer scanner to apply persistent runtime settings. (`adb reboot`)
