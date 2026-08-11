---
type: Playbook
sop_id: SOP-SYS-002
title: Resolution of OS Corruption using DISM and SFC
category: system
target_os: windows
description: Repairs operating system files, resolves application hangs, patches random
  BSOD errors, and restores core Windows stability using DISM and SFC tools.
required_entities: []
trigger_words:
- corruption
- BSOD
- system files
- DISM
- SFC
- repair
steps:
- step_number: 1
  sop_step_description: Check the local Windows image repository integrity using DISM
    ScanHealth.
  step_type: command
  command: DISM /Online /Cleanup-Image /ScanHealth
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: The operation completed successfully
  timeout_seconds: 90
  output_variable: dism_scan_health_output
  output_parse_instruction: Inspect output for 'component store corruption detected'
    or 'errors reported'. If present, set 'dism_scan_health_errors' to 'true'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Repair the Windows component store if corruption was detected
    in Step 1.
  step_type: command
  command: DISM /Online /Cleanup-Image /RestoreHealth
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: The restore operation completed successfully
  timeout_seconds: 300
  output_variable: dism_restore_health_output
  output_parse_instruction: Inspect output for 'restore operation completed successfully'.
    If not present, set 'dism_restore_failed' to 'true'.
  execute_if: variables.dism_scan_health_errors == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 3
  sop_step_description: Scan and repair active operating system files using System
    File Checker (SFC).
  step_type: command
  command: sfc /scannow
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Verification 100% complete
  timeout_seconds: 300
  output_variable: sfc_scannow_output
  output_parse_instruction: Inspect output for 'No integrity violations', 'Successfully
    repaired', or 'Unable to fix'. Set 'sfc_result' to 'healthy', 'repaired', or 'unable_to_fix'
    respectively.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 4
  sop_step_description: Safely restart the workstation to finalize repairs.
  step_type: command
  command: shutdown /r /t 0
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 30
  output_variable: null
  output_parse_instruction: null
  execute_if: null
  is_dangerous: true
  danger_warning: This step will immediately restart the system. Ensure all user data
    is saved before execution.
---

# Resolution of OS Corruption using DISM and SFC Playbook

## Overview
Repairs operating system files, resolves application hangs, patches random BSOD errors, and restores core Windows stability using DISM and SFC tools.

## Execution Steps
- **Step 1**: Check the local Windows image repository integrity using DISM ScanHealth. (`DISM /Online /Cleanup-Image /ScanHealth`)
- **Step 2**: Repair the Windows component store if corruption was detected in Step 1. (`DISM /Online /Cleanup-Image /RestoreHealth`)
- **Step 3**: Scan and repair active operating system files using System File Checker (SFC). (`sfc /scannow`)
- **Step 4**: Safely restart the workstation to finalize repairs. (`shutdown /r /t 0`)
