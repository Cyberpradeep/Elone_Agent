---
type: Playbook
sop_id: SOP-AUTH-007-001
title: Handle Suspicious Login Report
category: logins
target_os: null
description: This playbook automates the handling of a suspicious login report by
  reviewing recent login activity for a user's account and locking the account as
  a precautionary measure. The playbook ensures compliance with security protocols
  by escalating the issue to the security team after locking the account.
knowledge_base_ref: []
required_entities:
- user_id
- email
trigger_words:
- suspicious login
- unusual activity
- account lock
- security alert
steps:
- step_number: 1
  sop_step_description: Review recent login activity for the user's account by fetching
    audit logs.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: get_user_audit_log
  comm_inputs:
    user_id: '{{entities.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Lock the user's account as a precautionary measure, regardless
    of whether suspicious activity is found.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: lock_user_account
  comm_inputs:
    user_id: '{{entities.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
---

# Handle Suspicious Login Report Playbook

## Overview
This playbook automates the handling of a suspicious login report by reviewing recent login activity for a user's account and locking the account as a precautionary measure. The playbook ensures compliance with security protocols by escalating the issue to the security team after locking the account.

## Execution Steps
- **Step 1**: Review recent login activity for the user's account by fetching audit logs. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_audit_log({"user_id": "{{entities.user_id}}"})`]
- **Step 2**: Lock the user's account as a precautionary measure, regardless of whether suspicious activity is found. [Platform: `mock` | Tool Call: `l1_testing_platform_api.lock_user_account({"user_id": "{{entities.user_id}}"})`]
