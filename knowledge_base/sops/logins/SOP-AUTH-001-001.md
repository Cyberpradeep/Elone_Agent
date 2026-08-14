---
type: Playbook
sop_id: SOP-AUTH-001-001
title: How to Unlock a User's Account
category: logins
target_os: windows
description: This playbook automates the process of finding a user's account on the
  L1 Support Platform and unlocking it if it's locked due to repeated failed login
  attempts. It includes a critical check to prevent unlocking accounts that are flagged
  for security review, which require escalation.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- unlock
- account
- locked
- login issue
- user locked out
steps:
- step_number: 1
  sop_step_description: Search for the user's account on the L1 Support Platform using
    their email address to identify their user ID.
  step_type: tool_call
  platform: mock
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
  sop_step_description: Retrieve detailed profile information for the identified user
    to confirm their current lock status and check if the account is locked for a
    security review.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: get_user_details
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Unlock the user's account on the L1 Support Platform, which
    should reset failed login attempts and change the account status to 'Active'.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: unlock_user_account
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true' and variables.is_locked == 'true' and
    variables.status_is_security_review == 'false'
  timeout_seconds: 30
---

# How to Unlock a User's Account Playbook

## Overview
This playbook automates the process of finding a user's account on the L1 Support Platform and unlocking it if it's locked due to repeated failed login attempts. It includes a critical check to prevent unlocking accounts that are flagged for security review, which require escalation.

## Execution Steps
- **Step 1**: Search for the user's account on the L1 Support Platform using their email address to identify their user ID. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Retrieve detailed profile information for the identified user to confirm their current lock status and check if the account is locked for a security review. [Platform: `mock` | Tool Call: `l1_testing_platform_api.get_user_details({"user_id": "{{variables.user_id}}"})`]
- **Step 3**: Unlock the user's account on the L1 Support Platform, which should reset failed login attempts and change the account status to 'Active'. [Platform: `mock` | Tool Call: `l1_testing_platform_api.unlock_user_account({"user_id": "{{variables.user_id}}"})`]
