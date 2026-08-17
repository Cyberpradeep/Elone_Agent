---
type: Playbook
sop_id: SOP-stg-003-disk-error-diagnosis-and-repair-001
title: Disk Error Diagnosis and Repair via Chkdsk
category: storage
target_os: windows
description: This playbook automates the diagnosis and repair of filesystem structure
  corruption, bad logical storage blocks, and read/write drive anomalies on Windows
  HDDs and SSDs using chkdsk. It includes a rapid read-only scan, deep repair with
  error correction and sector recovery, and a forced reboot to initialize the repair
  scan.
knowledge_base_ref: []
required_entities:
- drive_letter
trigger_words:
- chkdsk
- disk error
- filesystem corruption
- sector repair
- reboot
steps:
- step_number: 1
  sop_step_description: Perform a rapid, non-intrusive read-only scan of the target
    drive to identify logical structural faults.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: 'chkdsk {{entities.drive_letter}}:'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Run a deep correction sequence to fix filesystem errors and
    recover unreadable data from degraded physical blocks.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: 'chkdsk {{entities.drive_letter}}: /f /r'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.anomalies_found == 'true'
  timeout_seconds: 300
- step_number: 3
  sop_step_description: Authorize the volume to be checked on the next system restart
    by confirming the reboot prompt.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: 'echo Y | chkdsk {{entities.drive_letter}}: /f /r'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.reboot_required == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Force an immediate reboot to initialize the repair scan.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: shutdown /r /t 0
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.reboot_required == 'true'
  timeout_seconds: 30
---

# Disk Error Diagnosis and Repair via Chkdsk Playbook

## Overview
This playbook automates the diagnosis and repair of filesystem structure corruption, bad logical storage blocks, and read/write drive anomalies on Windows HDDs and SSDs using chkdsk. It includes a rapid read-only scan, deep repair with error correction and sector recovery, and a forced reboot to initialize the repair scan.

## Execution Steps
- **Step 1**: Perform a rapid, non-intrusive read-only scan of the target drive to identify logical structural faults. (`chkdsk {{entities.drive_letter}}:`)
- **Step 2**: Run a deep correction sequence to fix filesystem errors and recover unreadable data from degraded physical blocks. (`chkdsk {{entities.drive_letter}}: /f /r`)
- **Step 3**: Authorize the volume to be checked on the next system restart by confirming the reboot prompt. (`echo Y | chkdsk {{entities.drive_letter}}: /f /r`)
- **Step 4**: Force an immediate reboot to initialize the repair scan. (`shutdown /r /t 0`)
