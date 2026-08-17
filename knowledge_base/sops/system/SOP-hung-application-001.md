---
type: Playbook
sop_id: SOP-hung-application-001
title: "Check and Terminate a Hung Application \u2013 Windows"
category: system
target_os: windows
description: This playbook verifies if a specified application is running on a Windows
  system and, if confirmed to be running and unresponsive, forcibly terminates its
  process.
knowledge_base_ref: []
required_entities:
- application_name
- application_executable
trigger_words:
- hung
- application
- terminate
- taskkill
- unresponsive
steps:
- step_number: 1
  sop_step_description: Verify the application is running by checking the process
    list.
  step_type: command
  platform: null
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
  sop_step_description: Force-terminate the application process if it was confirmed
    to be running.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM {{entities.application_executable}}
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.application_running == 'true'
  timeout_seconds: 30
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
This playbook verifies if a specified application is running on a Windows system and, if confirmed to be running and unresponsive, forcibly terminates its process.

## Execution Steps
- **Step 1**: Verify the application is running by checking the process list. (`tasklist | findstr "{{entities.application_name}}"`)
- **Step 2**: Force-terminate the application process if it was confirmed to be running. (`taskkill /F /IM {{entities.application_executable}}`)
