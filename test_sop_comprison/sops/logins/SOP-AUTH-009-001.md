---
type: Playbook
sop_id: SOP-AUTH-009-001
title: Find a User's Account Using Partial Details
category: logins
target_os: null
description: This playbook automates the process of searching for a user's account
  in the L1 Support Platform using partial details (e.g., partial email, name, or
  employee ID). It ensures the correct account is identified before proceeding with
  further actions.
knowledge_base_ref: []
required_entities:
- partial_detail
trigger_words:
- search
- user
- account
- partial detail
steps:
- step_number: 1
  sop_step_description: Search for user accounts using partial details provided by
    the user.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: search_users
  comm_inputs:
    email: '{{entities.partial_detail}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
---

# Find a User's Account Using Partial Details Playbook

## Overview
This playbook automates the process of searching for a user's account in the L1 Support Platform using partial details (e.g., partial email, name, or employee ID). It ensures the correct account is identified before proceeding with further actions.

## Execution Steps
- **Step 1**: Search for user accounts using partial details provided by the user. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.partial_detail}}"})`]
