---
type: Playbook
sop_id: SOP-L1-WIN-002
title: "Check and Terminate a Hung Application \u2013 Windows"
platform: system
category: software
target_os: windows
description: Automated workflow to verify if a specific application process is running
  and forcibly terminate it if detected.
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
  reason: Deterministic corrective command gated on process detection.
validation_confidence_score: 0.95
validation_confidence_level: High
validation_confidence_reason: All executable actions from the raw SOP are properly
  represented in the OKF steps with correct parameter mapping. No hallucinations,
  malicious commands, or prompt injection detected. The coverage ledger correctly
  accounts for GUI setup omission and command coverage.
injection_detected: false
injection_reasoning: ''
integrity_version: v2
integrity_hmac_sha256: 46ec3251d7731b3bee1afa53282f2271e551f8722d952e093f9f2761e9117d55
---

# Check and Terminate a Hung Application – Windows Playbook

## Overview
Automated workflow to verify if a specific application process is running and forcibly terminate it if detected.

## Execution Steps
- **Step 1**: Verify if the target application process is currently running. (`tasklist | findstr "{{entities.application}}"`)
- **Step 2**: Forcefully terminate the hung application process. (`taskkill /F /IM "{{entities.application}}.exe"`)
