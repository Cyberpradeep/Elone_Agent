---
type: Playbook
sop_id: SOP-APP-001
title: Software Application Unblock via IFEO Debugger Entry Removal
category: software
target_os: windows
description: Automated playbook to identify and remove Image File Execution Options
  (IFEO) debugger entries blocking approved software applications on Windows endpoints.
  Includes connectivity verification, registry inspection, remediation, and policy
  refresh.
required_entities:
- hostname
trigger_words:
- application blocked
- unblock software
- IFEO
- debugger entry
- registry block
steps:
- step_number: 1
  sop_step_description: Verify endpoint connectivity to ensure remote administrative
    access is possible.
  step_type: command
  command: Test-Connection {entities.computername} -Count 2
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Reply from
  timeout_seconds: 30
  output_variable: connectivity_check
  output_parse_instruction: Check if output contains 'Reply from'. If not, set 'connectivity_failure'
    to 'true'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Identify if the application is blocked via an IFEO Debugger
    entry by querying the registry.
  step_type: command
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{variables.application_exe}"
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains:
  - Debugger
  - ERROR
  timeout_seconds: 90
  output_variable: ifeo_query_result
  output_parse_instruction: 'Inspect output. If ''Debugger'' value is present, set
    ''ifeo_block_detected'' to ''true''. If ''ERROR: The system was unable to find
    the specified registry key'', set ''ifeo_block_detected'' to ''false''.'
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 3
  sop_step_description: Remove the IFEO Debugger entry if Step 2 confirms its presence.
  step_type: command
  command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{variables.application_exe}" /v Debugger /f
  shell: powershell
  fallback_command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image
    File Execution Options\{variables.application_exe}" /f
  fallback_sop_id: null
  expected_output_contains: The operation completed successfully
  timeout_seconds: 90
  output_variable: debugger_removal_result
  output_parse_instruction: Check if output contains 'The operation completed successfully'.
    If not, set 'removal_failed' to 'true'.
  execute_if: variables.ifeo_block_detected == 'true'
  is_dangerous: true
  danger_warning: This step modifies the Windows registry. Ensure the application
    is approved for unblocking before proceeding.
- step_number: 4
  sop_step_description: Refresh local Group Policy to apply changes immediately.
  step_type: command
  command: gpupdate /force
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Computer Policy update has completed successfully
  timeout_seconds: 300
  output_variable: policy_refresh_result
  output_parse_instruction: Check if output contains 'Computer Policy update has completed
    successfully'. If not, set 'policy_refresh_failed' to 'true'.
  execute_if: variables.ifeo_block_detected == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 5
  sop_step_description: Verify that the IFEO block has been removed by re-querying
    the registry.
  step_type: command
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{variables.application_exe}"
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: 'ERROR: The system was unable to find the specified registry
    key'
  timeout_seconds: 90
  output_variable: verification_query_result
  output_parse_instruction: 'Inspect output. If ''ERROR: The system was unable to
    find the specified registry key'' or no ''Debugger'' value is present, set ''block_removed''
    to ''true''.'
  execute_if: variables.ifeo_block_detected == 'true'
  is_dangerous: false
  danger_warning: null
---

# Software Application Unblock via IFEO Debugger Entry Removal Playbook

## Overview
Automated playbook to identify and remove Image File Execution Options (IFEO) debugger entries blocking approved software applications on Windows endpoints. Includes connectivity verification, registry inspection, remediation, and policy refresh.

## Execution Steps
- **Step 1**: Verify endpoint connectivity to ensure remote administrative access is possible. (`Test-Connection {entities.computername} -Count 2`)
- **Step 2**: Identify if the application is blocked via an IFEO Debugger entry by querying the registry. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{variables.application_exe}"`)
- **Step 3**: Remove the IFEO Debugger entry if Step 2 confirms its presence. (`reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{variables.application_exe}" /v Debugger /f`) [Fallback: `reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{variables.application_exe}" /f`]
- **Step 4**: Refresh local Group Policy to apply changes immediately. (`gpupdate /force`)
- **Step 5**: Verify that the IFEO block has been removed by re-querying the registry. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{variables.application_exe}"`)
