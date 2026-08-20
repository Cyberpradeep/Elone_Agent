---
type: Playbook
sop_id: SOP-L1-APP-001
title: Software Application Unblock Request
platform: system
category: software
target_os: windows
description: Standard operating procedure to identify and remediate software application
  blocks caused by Image File Execution Options (IFEO) debugger entries on Windows
  endpoints.
confidence_score: 0.95
confidence_level: High
confidence_reason: All actionable steps map directly to native Windows PowerShell
  and registry CLI commands with complete entity placeholders and explicit fallback
  mechanisms.
required_entities:
- hostname
- application_name
trigger_words:
- unblock
- application
- software
- IFEO
- debugger
- registry
- blocked
steps:
- step_number: 1
  sop_step_description: Verify endpoint network connectivity before performing registry
    operations.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: Test-Connection {{entities.hostname}} -Count 2
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Identify if the application is blocked using an Image File
    Execution Options (IFEO) Debugger registry entry.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_name}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Remove the IFEO Debugger registry value blocking application
    execution (with fallback to remove the entire key).
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_name}}.exe" /v Debugger /f
  fallback_command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image
    File Execution Options\{{entities.application_name}}.exe" /f
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_block_detected == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Refresh local and computer Group Policy to enforce updated
    endpoint configuration.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: gpupdate /force
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 90
- step_number: 5
  sop_step_description: Verify that the IFEO Debugger entry or key has been successfully
    removed.
  step_type: command
  platform: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_name}}.exe"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
---

# Software Application Unblock Request Playbook

## Overview
Standard operating procedure to identify and remediate software application blocks caused by Image File Execution Options (IFEO) debugger entries on Windows endpoints.

## Execution Steps
- **Step 1**: Verify endpoint network connectivity before performing registry operations. (`Test-Connection {{entities.hostname}} -Count 2`)
- **Step 2**: Identify if the application is blocked using an Image File Execution Options (IFEO) Debugger registry entry. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_name}}.exe"`)
- **Step 3**: Remove the IFEO Debugger registry value blocking application execution (with fallback to remove the entire key). (`reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_name}}.exe" /v Debugger /f`) [Fallback: `reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_name}}.exe" /f`]
- **Step 4**: Refresh local and computer Group Policy to enforce updated endpoint configuration. (`gpupdate /force`)
- **Step 5**: Verify that the IFEO Debugger entry or key has been successfully removed. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_name}}.exe"`)
