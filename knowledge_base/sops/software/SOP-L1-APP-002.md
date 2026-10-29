---
type: Playbook
sop_id: SOP-L1-APP-002
title: "Check and Terminate a Hung Application \u2013 Windows"
platform: system
category: software
target_os: windows
description: Automated workflow to verify if a specific application process is running
  and forcibly terminate it if confirmed.
confidence_score: 0.98
confidence_level: High
confidence_reason: All steps mapped to deterministic Windows PowerShell commands with
  exact variable linkage and conditional execution.
is_executable: true
unexecutable_reason: null
automation_status: fully_automated
required_entities:
- application
trigger_words:
- hung
- terminate
- taskkill
- tasklist
- unresponsive
- application
steps:
- step_number: 1
  sop_step_description: Verify if the target application process is currently running.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: tasklist | findstr "{{entities.application}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains '{{entities.application}}', set variables.process_running
    = true, else set variables.process_running = false
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: Forcefully terminate the hung application process.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM "{{entities.application}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.process_terminated = true, else
    set variables.process_terminated = false
  execute_if: variables.process_running == true
  timeout_seconds: 30
  shell: powershell
source_action_coverage:
- source_action: Open Command Prompt
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: GUI setup instruction omitted; execution environment is assumed to be PowerShell.
- source_action: Verify the application is running using tasklist | findstr
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Deterministic diagnostic command to check process existence.
- source_action: Terminate the application using taskkill /F /IM
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Deterministic corrective command to force terminate the process.
document_metadata: {}
integrity_version: v2
integrity_hmac_sha256: ef6f8a4c3ea5492074c8f9b7b1b10e51dde56e66ba136a26c5b7815fb183e3e2
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Automated workflow to verify if a specific application process is running and forcibly terminate it if confirmed.

## Execution Steps
- **Step 1**: Verify if the target application process is currently running. (`tasklist | findstr "{{entities.application}}"`)
- **Step 2**: Forcefully terminate the hung application process. (`taskkill /F /IM "{{entities.application}}.exe"`)
