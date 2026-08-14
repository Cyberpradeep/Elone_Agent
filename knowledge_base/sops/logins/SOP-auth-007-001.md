---
type: Playbook
sop_id: SOP-auth-007-001
title: Handle Suspicious Login Report
category: logins
target_os: null
description: Locks a user account and retrieves audit logs for suspicious login activity,
  then escalates to security team. Automated steps include account lookup, audit log
  retrieval, and account locking.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- suspicious login
- security alert
- unusual activity
- audit log
steps:
- step_number: 1
  sop_step_description: Search for the user account by email to confirm existence
    and retrieve user_id.
  step_type: tool_call
  platform: l1_testing_platform_api
  provider: l1_testing_platform_api
  function_name: search_users
  comm_inputs:
    email: '{{entities.email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Retrieve the user's audit log to review recent login activity
    for suspicious entries.
  step_type: tool_call
  platform: l1_testing_platform_api
  provider: l1_testing_platform_api
  function_name: get_user_audit_log
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.account_found == 'true'
  timeout_seconds: 90
- step_number: 3
  sop_step_description: Lock the user account as a precautionary measure to prevent
    further access during investigation.
  step_type: tool_call
  platform: l1_testing_platform_api
  provider: l1_testing_platform_api
  function_name: lock_user_account
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.account_found == 'true'
  timeout_seconds: 30
---

# Handle Suspicious Login Report Playbook

## Overview
Locks a user account and retrieves audit logs for suspicious login activity, then escalates to security team. Automated steps include account lookup, audit log retrieval, and account locking.

## Execution Steps
- **Step 1**: Search for the user account by email to confirm existence and retrieve user_id. [Platform: `l1_testing_platform_api` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Retrieve the user's audit log to review recent login activity for suspicious entries. [Platform: `l1_testing_platform_api` | Tool Call: `l1_testing_platform_api.get_user_audit_log({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Lock the user account as a precautionary measure to prevent further access during investigation. [Platform: `l1_testing_platform_api` | Tool Call: `l1_testing_platform_api.lock_user_account({"user_id": "{{variables.user_id}}"})`]
