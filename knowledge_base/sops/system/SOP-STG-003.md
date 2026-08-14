---
type: Playbook
sop_id: SOP-STG-003
title: Disk Error Diagnosis and Repair via Chkdsk
category: system
target_os: windows
description: To identify and repair filesystem structure corruption, bad logical storage
  blocks, and read/write drive anomalies causing performance bottlenecks on client
  storage assets (HDDs and SSDs) experiencing extreme latency or error warnings.
knowledge_base_ref: []
required_entities:
- hostname
trigger_words:
- disk error
- chkdsk
- repair
- latency
- drive anomalies
- filesystem corruption
- bad blocks
- storage errors
steps:
- step_number: 1
  sop_step_description: Perform a rapid, non-intrusive read-only scan of the root
    target drive (C:) to identify if logical structural faults exist.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: 'chkdsk C:'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 90
- step_number: 2
  sop_step_description: 'If integrity or sector anomalies are found, run the deep
    correction sequence (`chkdsk C: /f /r`) and automatically authorize the volume
    reboot schedule by providing ''Y'' to the prompt. This flags errors for correction
    and uncovers unreadable data.'
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: 'echo Y | chkdsk C: /f /r'
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.logical_faults_found == 'true'
  timeout_seconds: 300
- step_number: 3
  sop_step_description: Execute a direct reboot to pass control to the Windows boot
    scanner and initialize the scheduled repair scan.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: shutdown /r /t 0
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.repair_scheduled == 'true'
  timeout_seconds: 30
---

# Disk Error Diagnosis and Repair via Chkdsk Playbook

## Overview
To identify and repair filesystem structure corruption, bad logical storage blocks, and read/write drive anomalies causing performance bottlenecks on client storage assets (HDDs and SSDs) experiencing extreme latency or error warnings.

## Execution Steps
- **Step 1**: Perform a rapid, non-intrusive read-only scan of the root target drive (C:) to identify if logical structural faults exist. (`chkdsk C:`)
- **Step 2**: If integrity or sector anomalies are found, run the deep correction sequence (`chkdsk C: /f /r`) and automatically authorize the volume reboot schedule by providing 'Y' to the prompt. This flags errors for correction and uncovers unreadable data. (`echo Y | chkdsk C: /f /r`)
- **Step 3**: Execute a direct reboot to pass control to the Windows boot scanner and initialize the scheduled repair scan. (`shutdown /r /t 0`)
