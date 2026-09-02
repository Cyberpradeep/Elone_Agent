---
type: Playbook
sop_id: SOP-L1-APP-001
title: Software Application Unblock Request
platform: system
category: software
target_os: windows
description: Automated workflow to verify endpoint connectivity, inspect registry
  for IFEO Debugger blocks, remove the block, refresh policy, and verify removal.
confidence_score: 0.98
confidence_level: High
confidence_reason: All steps mapped to deterministic Windows PowerShell commands with
  exact variable linkage and fallback delete handling. Human interaction steps omitted.
is_executable: true
unexecutable_reason: null
required_entities:
- hostname
- application
trigger_words:
- ifeo
- unblock
- application
- debugger
- registry
- block
steps:
- step_number: 1
  sop_step_description: Verify endpoint network connectivity before performing remote
    diagnostics.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Test-Connection {{entities.hostname}} -Count 2
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If ping replies are received, set variables.endpoint_reachable
    = true, else set variables.endpoint_reachable = false
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: Query IFEO registry key to check if application is blocked
    by a Debugger entry.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Debugger', set variables.ifeo_blocked = true,
    else set variables.ifeo_blocked = false
  execute_if: variables.endpoint_reachable == true
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Remove IFEO Debugger registry value or full key to unblock
    execution.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application}}.exe" /v Debugger /f
  fallback_command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image
    File Execution Options\{{entities.application}}.exe" /f
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.block_removed = true, else set
    variables.block_removed = false
  execute_if: variables.ifeo_blocked == true
  timeout_seconds: 30
  shell: powershell
- step_number: 4
  sop_step_description: Refresh local Group Policy to apply unblock changes immediately.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: gpupdate /force
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_blocked == true
  timeout_seconds: 90
  shell: powershell
- step_number: 5
  sop_step_description: Verify IFEO block removal by re-querying the target registry
    key.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Debugger', set variables.block_verified =
    false, else set variables.block_verified = true
  execute_if: variables.ifeo_blocked == true
  timeout_seconds: 30
  shell: powershell
---

# Software Application Unblock Request Playbook

## Overview
Automated workflow to verify endpoint connectivity, inspect registry for IFEO Debugger blocks, remove the block, refresh policy, and verify removal.

## Execution Steps
- **Step 1**: Verify endpoint network connectivity before performing remote diagnostics. (`Test-Connection {{entities.hostname}} -Count 2`)
- **Step 2**: Query IFEO registry key to check if application is blocked by a Debugger entry. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe"`)
- **Step 3**: Remove IFEO Debugger registry value or full key to unblock execution. (`reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe" /v Debugger /f`) [Fallback: `reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe" /f`]
- **Step 4**: Refresh local Group Policy to apply unblock changes immediately. (`gpupdate /force`)
- **Step 5**: Verify IFEO block removal by re-querying the target registry key. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe"`)
