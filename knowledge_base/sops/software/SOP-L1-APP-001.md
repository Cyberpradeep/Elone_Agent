---
type: Playbook
sop_id: SOP-L1-APP-001
title: Software Application Unblock Request (IFEO Debugger Entry Removal)
category: software
target_os: windows
description: This playbook automates the identification and removal of an Image File
  Execution Options (IFEO) debugger entry blocking a software application on a Windows
  endpoint. It includes connectivity checks, registry queries, block removal, policy
  refresh, and verification.
knowledge_base_ref: []
required_entities:
- hostname
- executable
trigger_words:
- unblock
- application
- IFEO
- debugger
- registry
steps:
- step_number: 1
  sop_step_description: Verify endpoint connectivity using Test-Connection.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: Test-Connection {{entities.computer_name}} -Count 2
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Identify if the application is blocked by an IFEO Debugger
    entry.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_exe}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.connectivity_confirmed == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Remove the IFEO Debugger entry if it exists.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_exe}}" /v Debugger /f
  fallback_command: reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image
    File Execution Options\{{entities.application_exe}}" /f
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_block_found == 'true'
  timeout_seconds: 90
- step_number: 4
  sop_step_description: Refresh local Group Policy to apply changes.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: gpupdate /force
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_block_removed == 'true'
  timeout_seconds: 120
- step_number: 5
  sop_step_description: Verify that the IFEO Debugger entry has been removed.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File
    Execution Options\{{entities.application_exe}}"
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ifeo_block_removed == 'true'
  timeout_seconds: 30
---

# Software Application Unblock Request (IFEO Debugger Entry Removal) Playbook

## Overview
This playbook automates the identification and removal of an Image File Execution Options (IFEO) debugger entry blocking a software application on a Windows endpoint. It includes connectivity checks, registry queries, block removal, policy refresh, and verification.

## Execution Steps
- **Step 1**: Verify endpoint connectivity using Test-Connection. (`Test-Connection {{entities.computer_name}} -Count 2`)
- **Step 2**: Identify if the application is blocked by an IFEO Debugger entry. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_exe}}"`)
- **Step 3**: Remove the IFEO Debugger entry if it exists. (`reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_exe}}" /v Debugger /f`) [Fallback: `reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_exe}}" /f`]
- **Step 4**: Refresh local Group Policy to apply changes. (`gpupdate /force`)
- **Step 5**: Verify that the IFEO Debugger entry has been removed. (`reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\{{entities.application_exe}}"`)
