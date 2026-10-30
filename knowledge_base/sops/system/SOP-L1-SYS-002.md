---
type: Playbook
sop_id: SOP-L1-SYS-002
title: Temporary Directory Cleanup Procedure
platform: system
category: system
target_os: windows
description: Automated workflow to identify, list, and remove stale files older than
  seven days from the system scratch directory, followed by disk usage verification.
confidence_score: 0.95
confidence_level: High
confidence_reason: All steps mapped to deterministic PowerShell commands. Linux 'find'
  and 'df' commands translated to native PowerShell equivalents (Get-ChildItem, Remove-Item,
  Get-PSDrive).
is_executable: true
unexecutable_reason: null
automation_status: fully_automated
required_entities:
- scratch_path
trigger_words:
- cleanup
- temporary
- scratch
- stale
- disk
- tmp
steps:
- step_number: 1
  sop_step_description: Verify the target temporary folder path exists.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Test-Path -Path '{{entities.scratch_path}}'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout is 'True', set variables.path_exists = true, else set
    variables.path_exists = false
  execute_if: null
  timeout_seconds: 10
  shell: powershell
- step_number: 2
  sop_step_description: List stale files older than seven days in the scratch directory.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Get-ChildItem -Path '{{entities.scratch_path}}' -File | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Select-Object Name, LastWriteTime,
    Length
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout is not empty, set variables.stale_files_found = true,
    else set variables.stale_files_found = false
  execute_if: variables.path_exists == true
  timeout_seconds: 30
  shell: powershell
- step_number: 3
  sop_step_description: Remove stale temporary files older than seven days.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Get-ChildItem -Path '{{entities.scratch_path}}' -File | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.cleanup_completed = true, else
    set variables.cleanup_completed = false
  execute_if: variables.path_exists == true AND variables.stale_files_found == true
  timeout_seconds: 60
  shell: powershell
- step_number: 4
  sop_step_description: Verify remaining disk usage on the drive containing the scratch
    directory.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Get-PSDrive -Name (Get-Item '{{entities.scratch_path}}').PSDrive.Name |
    Select-Object Name, Used, Free
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.path_exists == true
  timeout_seconds: 10
  shell: powershell
source_action_coverage:
- source_action: Identify target temporary folder path at /var/tmp/scratch
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Translated to Test-Path to verify existence of the target directory.
- source_action: Search and list stale files older than seven days using find /var/tmp/scratch
    -type f -mtime +7
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Translated to Get-ChildItem with LastWriteTime filter to list stale files.
- source_action: Remove stale temporary files using find /var/tmp/scratch -type f
    -mtime +7 -delete
  coverage: command_covered
  step_number: 3
  tool: null
  condition: null
  reason: Translated to Remove-Item to delete files older than 7 days.
- source_action: Verify remaining disk usage using df -h /var/tmp
  coverage: command_covered
  step_number: 4
  tool: null
  condition: null
  reason: Translated to Get-PSDrive to check free space on the drive containing the
    scratch path.
document_metadata: {}
integrity_version: v2
integrity_hmac_sha256: ed4074aff355d3ba8d5979c93264a919bb807c13f44c3dec7e533a221ad8b4f2
---

# Temporary Directory Cleanup Procedure Playbook

## Overview
Automated workflow to identify, list, and remove stale files older than seven days from the system scratch directory, followed by disk usage verification.

## Execution Steps
- **Step 1**: Verify the target temporary folder path exists. (`Test-Path -Path '{{entities.scratch_path}}'`)
- **Step 2**: List stale files older than seven days in the scratch directory. (`Get-ChildItem -Path '{{entities.scratch_path}}' -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Select-Object Name, LastWriteTime, Length`)
- **Step 3**: Remove stale temporary files older than seven days. (`Get-ChildItem -Path '{{entities.scratch_path}}' -File | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force`)
- **Step 4**: Verify remaining disk usage on the drive containing the scratch directory. (`Get-PSDrive -Name (Get-Item '{{entities.scratch_path}}').PSDrive.Name | Select-Object Name, Used, Free`)
