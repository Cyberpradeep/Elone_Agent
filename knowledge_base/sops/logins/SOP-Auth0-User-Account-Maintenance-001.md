---
type: Playbook
sop_id: SOP-Auth0-User-Account-Maintenance-001
title: Auth0 User Account Maintenance Procedure
category: logins
target_os: windows
description: Procedure to search for an Auth0 user account, check its locked status,
  and unlock it if necessary, followed by verification.
knowledge_base_ref:
- url: http://example.com
  file_path: knowledge_base/logs/web_cache/a9b9f04336ce0181a08e774e01113b31.log
required_entities:
- email
trigger_words:
- auth0
- unlock
- account
- locked
- login
steps:
- step_number: 1
  sop_step_description: Search for user account using customer email in the platform.
  step_type: tool_call
  platform: auth0
  provider: auth0_user_management
  function_name: search_user
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: If locked, unlock the user account using the admin unlock
    tool.
  step_type: tool_call
  platform: auth0
  provider: auth0_user_management
  function_name: unlock_user_account
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_locked == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Verify account status is updated to unlocked.
  step_type: tool_call
  platform: auth0
  provider: auth0_user_management
  function_name: search_user
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.unlock_success == 'true'
  timeout_seconds: 30
---

# Auth0 User Account Maintenance Procedure Playbook

## Overview
Procedure to search for an Auth0 user account, check its locked status, and unlock it if necessary, followed by verification.

## Knowledge Base References
- [http://example.com](http://example.com) — Knowledge File: `knowledge_base/logs/web_cache/a9b9f04336ce0181a08e774e01113b31.log`

## Execution Steps
- **Step 1**: Search for user account using customer email in the platform. [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
- **Step 2**: If locked, unlock the user account using the admin unlock tool. [Platform: `auth0` | Tool Call: `auth0_user_management.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Verify account status is updated to unlocked. [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
