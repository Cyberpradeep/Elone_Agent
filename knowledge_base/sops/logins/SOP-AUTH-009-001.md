---
type: Playbook
sop_id: SOP-AUTH-009-001
title: Find User Account with Partial Details
category: logins
target_os: null
description: Search for a user account in the L1 Support Platform using partial details
  (name, partial email, etc.) to identify the correct account before proceeding with
  further actions.
knowledge_base_ref: []
required_entities:
- partial_email
trigger_words:
- search
- user
- account
- partial
- email
steps:
- step_number: 1
  sop_step_description: Search for user accounts using partial details provided by
    the user.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: search_users
  comm_inputs:
    email: '{{entities.partial_email}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
---

# Find User Account with Partial Details Playbook

## Overview
Search for a user account in the L1 Support Platform using partial details (name, partial email, etc.) to identify the correct account before proceeding with further actions.

## Execution Steps
- **Step 1**: Search for user accounts using partial details provided by the user. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.partial_email}}"})`]
