---
type: Playbook
sop_id: SOP-L1-APP-002
title: "Check and Terminate a Hung Application \u2013 Windows"
platform: system
category: software
target_os: windows
description: Automated workflow to verify if a specified application process is running
  and, if so, to forcibly terminate it.
confidence_score: 0.98
confidence_level: High
confidence_reason: All steps mapped to deterministic Windows PowerShell commands with
  exact variable linkage and conditional execution.
is_executable: true
unexecutable_reason: null
required_entities:
- application_name
trigger_words:
- terminate
- hung
- application
- taskkill
- tasklist
steps:
- step_number: 1
  sop_step_description: Verify if the specified application process is currently running.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: tasklist | findstr "{{entities.application_name}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains '{{entities.application_name}}', set variables.app_running
    = true, else set variables.app_running = false
  execute_if: null
  timeout_seconds: 30
  shell: powershell
- step_number: 2
  sop_step_description: Forcibly terminate the identified hung application process.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM "{{entities.application_name}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If exit code is 0, set variables.app_terminated = true, else
    set variables.app_terminated = false
  execute_if: variables.app_running == true
  timeout_seconds: 30
  shell: powershell
integrity_hmac_sha256: ebff6b65911fa3b89fb7a873cec10f5be76b3651fb714d38dda0bb63ec9e484a
integrity_version: v2
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Automated workflow to verify if a specified application process is running and, if so, to forcibly terminate it.

## Execution Steps
- **Step 1**: Verify if the specified application process is currently running. (`tasklist | findstr "{{entities.application_name}}"`)
- **Step 2**: Forcibly terminate the identified hung application process. (`taskkill /F /IM "{{entities.application_name}}.exe"`)
