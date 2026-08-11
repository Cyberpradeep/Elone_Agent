---
type: Playbook
sop_id: SOP-STG-003
title: Disk Error Diagnosis and Repair via Chkdsk
category: storage
target_os: windows
description: Identifies and repairs filesystem corruption, bad sectors, and read/write
  anomalies on HDDs/SSDs using chkdsk. Includes read-only diagnostic, deep repair,
  and reboot steps with user authorization checks.
required_entities: []
trigger_words:
- disk
- chkdsk
- storage
- corruption
- bad sectors
- latency
steps:
- step_number: 1
  sop_step_description: Perform a rapid, non-intrusive read-only scan of the target
    drive to identify logical structural faults or sector anomalies.
  step_type: command
  command: 'chkdsk C:'
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Windows has scanned the file system and found no problems
  timeout_seconds: 30
  output_variable: chkdsk_readonly_output
  output_parse_instruction: Inspect output for phrases like 'corrupt', 'bad sectors',
    or 'errors found'. If anomalies detected, set 'disk_anomalies_detected' to 'true'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: If anomalies are detected in Step 1, schedule a deep file
    system and sector repair scan requiring a reboot.
  step_type: command
  command: 'chkdsk C: /f /r'
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Would you like to schedule this volume to be checked the
    next time the system restarts?
  timeout_seconds: 300
  output_variable: chkdsk_repair_output
  output_parse_instruction: Capture the prompt for reboot confirmation. If prompt
    appears, set 'reboot_required' to 'true'.
  execute_if: variables.disk_anomalies_detected == 'true'
  is_dangerous: true
  danger_warning: This step will schedule a disk repair requiring a system reboot.
    Ensure user authorization for downtime.
- step_number: 3
  sop_step_description: Respond 'Y' to the reboot confirmation prompt to schedule
    the disk check on next restart.
  step_type: command
  command: echo Y
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 30
  output_variable: null
  output_parse_instruction: null
  execute_if: variables.reboot_required == 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 4
  sop_step_description: Force an immediate reboot to initiate the scheduled disk repair
    scan.
  step_type: command
  command: shutdown /r /t 0
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 30
  output_variable: null
  output_parse_instruction: null
  execute_if: variables.reboot_required == 'true'
  is_dangerous: true
  danger_warning: This step will immediately reboot the system. Ensure all user data
    is saved and authorization is confirmed.
---

# Disk Error Diagnosis and Repair via Chkdsk Playbook

## Overview
Identifies and repairs filesystem corruption, bad sectors, and read/write anomalies on HDDs/SSDs using chkdsk. Includes read-only diagnostic, deep repair, and reboot steps with user authorization checks.

## Execution Steps
- **Step 1**: Perform a rapid, non-intrusive read-only scan of the target drive to identify logical structural faults or sector anomalies. (`chkdsk C:`)
- **Step 2**: If anomalies are detected in Step 1, schedule a deep file system and sector repair scan requiring a reboot. (`chkdsk C: /f /r`)
- **Step 3**: Respond 'Y' to the reboot confirmation prompt to schedule the disk check on next restart. (`echo Y`)
- **Step 4**: Force an immediate reboot to initiate the scheduled disk repair scan. (`shutdown /r /t 0`)
