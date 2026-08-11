---
type: Playbook
sop_id: SOP-DYN-001
title: "Check and Terminate a Hung Application \u2013 Windows"
category: software
target_os: windows
description: Verifies if a specified application process is running and forcibly terminates
  it if unresponsive. Ensures immediate recovery of system resources while warning
  of potential data loss.
required_entities: []
trigger_words:
- hung
- unresponsive
- application
- terminate
- force close
steps:
- step_number: 1
  sop_step_description: Verify if the specified application process is currently running by checking the process list.
  step_type: command
  command: tasklist | findstr /I {entities.executable}
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: ApplicationName.exe
  timeout_seconds: 30
  output_variable: tasklist_output
  output_parse_instruction: Inspect output. If process name is found, set 'process_exists' to 'true'. If no output, set 'process_exists' to 'false'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: "Forcefully terminate the application process to recover system resources. Warning: Unsaved data may be lost."
  step_type: command
  command: taskkill /F /IM {entities.executable}
  shell: cmd
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: 'SUCCESS: Sent termination signal'
  timeout_seconds: 30
  output_variable: taskkill_output
  output_parse_instruction: No parsing required. Confirm termination success via output message.
  execute_if: variables.process_exists == 'true'
  is_dangerous: true
  danger_warning: This step will forcefully terminate the application. Any unsaved data in the application may be lost.
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Verifies if a specified application process is running and forcibly terminates it if unresponsive. Ensures immediate recovery of system resources while warning of potential data loss.

## Execution Steps
- **Step 1**: Verify if the specified application process is currently running by checking the process list. (`tasklist | findstr /I {entities.executable}`)
- **Step 2**: Forcefully terminate the application process to recover system resources. Warning: Unsaved data may be lost. (`taskkill /F /IM {entities.executable}`)

