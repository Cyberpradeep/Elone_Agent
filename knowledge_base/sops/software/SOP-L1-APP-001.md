---
type: Playbook
sop_id: SOP-L1-APP-001
title: Software Application Unblock Request
platform: system
category: software
target_os: windows
description: Automated procedure to identify and remove Image File Execution Options
  (IFEO) debugger blocking entries for approved applications on Windows endpoints,
  refresh local policy, and verify remediation.
confidence_score: 0.95
confidence_level: High
confidence_reason: All procedural steps map directly to standard Windows CLI and PowerShell
  commands. Entity parameters (hostname and application) are clearly defined, and
  conditional logic cleanly gates the remediation action.
required_entities:
- hostname
- application
trigger_words:
- unblock
- application
- ifeo
- debugger
- registry
- gpupdate
steps:
- step_number: 1
  sop_step_description: Verify endpoint network connectivity using Test-Connection
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Test-Connection {{entities.hostname}} -Count 2
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'Reply', set variables.host_reachable = true,
    else set variables.host_reachable = false
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Query registry for Image File Execution Options (IFEO) debugger
    entry for the application
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
  execute_if: null
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Remove the IFEO Debugger registry value blocking application
    launch
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application}}.exe" /v Debugger /f
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_blocked == true
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Force local Group Policy refresh to apply configuration changes
    immediately
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
- step_number: 5
  sop_step_description: Verify IFEO block removal by querying registry again
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains 'ERROR' or does not contain 'Debugger', set
    variables.unblock_verified = true, else set variables.unblock_verified = false
  execute_if: variables.ifeo_blocked == true
  timeout_seconds: 30
---

# Software Application Unblock Request Playbook

## Overview
Automated procedure to identify and remove Image File Execution Options (IFEO) debugger blocking entries for approved applications on Windows endpoints, refresh local policy, and verify remediation.

## Execution Steps
- **Step 1**: Verify endpoint network connectivity using Test-Connection (`Test-Connection {{entities.hostname}} -Count 2`)
- **Step 2**: Query registry for Image File Execution Options (IFEO) debugger entry for the application (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe"`)
- **Step 3**: Remove the IFEO Debugger registry value blocking application launch (`reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe" /v Debugger /f`)
- **Step 4**: Force local Group Policy refresh to apply configuration changes immediately (`gpupdate /force`)
- **Step 5**: Verify IFEO block removal by querying registry again (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application}}.exe"`)
