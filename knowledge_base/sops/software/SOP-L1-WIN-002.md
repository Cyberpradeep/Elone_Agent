---
type: Playbook
sop_id: SOP-L1-WIN-002
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
  sop_step_description: Verify the application process is currently running on the
    system.
  source_quote: tasklist | findstr "ApplicationName"
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
  source_quote: taskkill /F /IM ApplicationName.exe
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM "{{entities.application}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.process_running == true
  timeout_seconds: 30
  shell: powershell
source_action_coverage:
- source_action: Open Command Prompt and run the command below, replacing ApplicationName
    with the actual process name.
  coverage: manual_ui_omitted
  step_number: null
  tool: null
  condition: null
  reason: GUI setup instruction omitted; command execution is handled by the automation
    engine.
- source_action: tasklist | findstr "ApplicationName"
  coverage: command_covered
  step_number: 1
  tool: null
  condition: null
  reason: Diagnostic command to verify process existence.
- source_action: Once confirmed, force-terminate the process using the command below.
  coverage: command_covered
  step_number: 2
  tool: null
  condition: null
  reason: Corrective command to terminate the process, gated on diagnostic result.
document_metadata: {}
integrity_version: v2
integrity_hmac_sha256: 848db8c9a25d39907be315011ca97a2efc0ced358202dfc2d50a8d29129cc792
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Automated workflow to verify if a specific application process is running and forcibly terminate it if confirmed.

## Execution Steps
- **Step 1**: Verify the application process is currently running on the system. (`tasklist | findstr "{{entities.application}}"`)
- **Step 2**: Forcefully terminate the hung application process. (`taskkill /F /IM "{{entities.application}}.exe"`)
