---
type: Playbook
sop_id: SOP-auth0-user-account-maintenance-procedure-001
title: Auth0 User Account Maintenance Procedure
category: logins
target_os: windows
description: This playbook automates the process of searching for an Auth0 user account
  by email, checking if the account is locked, unlocking it if necessary, and verifying
  the updated status.
knowledge_base_ref:
- url: http://example.com
  file_path: knowledge_base/logs/web_cache/a9b9f04336ce0181a08e774e01113b31.log
required_entities:
- email
- user_id
trigger_words:
- auth0
- unlock
- account
- login
steps:
- step_number: 1
  sop_step_description: Search for user account using customer email in Auth0.
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
  sop_step_description: Check if the user account status is locked.
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
  execute_if: variables.account_found == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Unlock the user account if it is locked.
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
  execute_if: variables.account_locked == 'true'
  timeout_seconds: 30
- step_number: 4
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
This playbook automates the process of searching for an Auth0 user account by email, checking if the account is locked, unlocking it if necessary, and verifying the updated status.

## Knowledge Base References
- [http://example.com](http://example.com) — Knowledge File: `knowledge_base/logs/web_cache/a9b9f04336ce0181a08e774e01113b31.log`

## Execution Steps
- **Step 1**: Search for user account using customer email in Auth0. [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
- **Step 2**: Check if the user account status is locked. [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
- **Step 3**: Unlock the user account if it is locked. [Platform: `auth0` | Tool Call: `auth0_user_management.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
- **Step 4**: Verify account status is updated to unlocked. [Platform: `auth0` | Tool Call: `auth0_user_management.search_user({"email": "{{entities.email}}"})`]
