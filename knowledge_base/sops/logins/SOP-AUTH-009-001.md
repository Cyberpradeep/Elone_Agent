---
type: Playbook
sop_id: SOP-AUTH-009-001
title: Find User Account with Partial Details
category: logins
target_os: null
description: Search for a user account using partial details (e.g., partial email,
  name) to identify the correct account before proceeding with further actions.
required_entities:
- email
trigger_words:
- search
- user
- account
- partial
- email
steps:
- step_number: 1
  sop_step_description: Search for user accounts using partial email or other details
    provided by the user.
  step_type: tool_call
  provider: mock_support_platform
  function_name: search_users
  comm_inputs:
    email: '{entities.email}'
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: users
  timeout_seconds: 30
  output_variable: search_results
  output_parse_instruction: Inspect the JSON response for 'users' array. If users
    are found, set 'account_found' to 'true' and store the list of users in variables.user_matches.
    If no users are found, set 'account_found' to 'false'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Verify the correct account with the user by comparing details
    (e.g., full name, department) from the search results.
  step_type: verification
  provider: null
  function_name: null
  comm_inputs: null
  command: null
  shell: null
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: null
  timeout_seconds: 30
  output_variable: account_confirmed
  output_parse_instruction: Manually confirm with the user which account matches their
    details. Set 'account_confirmed' to 'true' if confirmed, otherwise 'false'.
  execute_if: variables.account_found == 'true'
  is_dangerous: false
  danger_warning: null
---

# Find User Account with Partial Details Playbook

## Overview
Search for a user account using partial details (e.g., partial email, name) to identify the correct account before proceeding with further actions.

## Execution Steps
- **Step 1**: Search for user accounts using partial email or other details provided by the user. [Tool Call: `mock_support_platform.search_users({"email": "{entities.email}"})`]
- **Step 2**: Verify the correct account with the user by comparing details (e.g., full name, department) from the search results. (`(none)`)
