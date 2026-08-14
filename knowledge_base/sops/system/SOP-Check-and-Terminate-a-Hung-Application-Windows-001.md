---
type: Playbook
sop_id: SOP-Check-and-Terminate-a-Hung-Application-Windows-001
title: "Check and Terminate a Hung Application \u2013 Windows"
category: system
target_os: windows
description: This procedure describes the standard steps to verify that an application
  is running and to forcibly terminate it when it has stopped responding (hung).
knowledge_base_ref: []
required_entities:
- application_name
trigger_words:
- hung application
- terminate application
- unresponsive app
- taskkill
steps:
- step_number: 1
  sop_step_description: Verify the application is running by listing active processes
    and filtering for the specified application name.
  step_type: command
  platform: windows
  provider: null
  function_name: null
  comm_inputs: null
  command: tasklist | findstr "{{entities.application_name}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Force-terminate the unresponsive application process.
  step_type: command
  platform: windows
  provider: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM "{{entities.application_name}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.app_running == 'true'
  timeout_seconds: 90
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
This procedure describes the standard steps to verify that an application is running and to forcibly terminate it when it has stopped responding (hung).

## Execution Steps
- **Step 1**: Verify the application is running by listing active processes and filtering for the specified application name. (`tasklist | findstr "{{entities.application_name}}"`)
- **Step 2**: Force-terminate the unresponsive application process. (`taskkill /F /IM "{{entities.application_name}}.exe"`)
