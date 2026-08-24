---
type: Playbook
sop_id: SOP-check-and-terminate-hung-application-001
title: "Check and Terminate a Hung Application \u2013 Windows"
platform: system
category: system
target_os: windows
description: This playbook verifies if a specified application is running on a Windows
  system and, if confirmed, forcibly terminates the unresponsive process.
confidence_score: 0.95
confidence_level: High
confidence_reason: The raw SOP clearly outlines two distinct steps that directly translate
  to standard Windows CLI commands. All required parameters are explicitly mentioned
  and mappable to entities, and the conditional logic is straightforward.
required_entities:
- application_name
trigger_words:
- hung
- terminate
- application
- unresponsive
- taskkill
- tasklist
steps:
- step_number: 1
  sop_step_description: Verify the application is running by listing processes and
    filtering for the application name.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: tasklist | findstr "{{{{entities.application_name}}}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Force-terminate the application process using its executable
    name.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: taskkill /F /IM "{{{{entities.application_name}}}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.application_running == 'true'
  timeout_seconds: 30
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
This playbook verifies if a specified application is running on a Windows system and, if confirmed, forcibly terminates the unresponsive process.

## Execution Steps
- **Step 1**: Verify the application is running by listing processes and filtering for the application name. (`tasklist | findstr "{{{{entities.application_name}}}}"`)
- **Step 2**: Force-terminate the application process using its executable name. (`taskkill /F /IM "{{{{entities.application_name}}}}.exe"`)
