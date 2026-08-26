---
type: Playbook
sop_id: SOP-check-and-terminate-a-hung-application-windows-001
title: "Check and Terminate a Hung Application \u2013 Windows"
platform: windows
category: software
target_os: windows
description: Standard operating procedure to verify whether a target Windows desktop
  application is running and forcibly terminate it if unresponsive.
confidence_score: 0.95
confidence_level: High
confidence_reason: All steps map directly to standard native Windows CLI commands
  (tasklist and taskkill) with clear diagnostic output parsing and conditional remediation
  gating.
required_entities:
- application
trigger_words:
- windows
- terminate
- hung
- application
- taskkill
- tasklist
- unresponsive
- force kill
steps:
- step_number: 1
  sop_step_description: Verify the target application process is running using tasklist.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: tasklist | findstr "{{entities.application}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: If stdout contains '{{entities.application}}', set variables.application_running
    = true, else set variables.application_running = false
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Force-terminate the application process using taskkill.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM {{entities.application}}.exe
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.application_running == true
  timeout_seconds: 30
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Standard operating procedure to verify whether a target Windows desktop application is running and forcibly terminate it if unresponsive.

## Execution Steps
- **Step 1**: Verify the target application process is running using tasklist. (`tasklist | findstr "{{entities.application}}"`)
- **Step 2**: Force-terminate the application process using taskkill. (`taskkill /F /IM {{entities.application}}.exe`)
