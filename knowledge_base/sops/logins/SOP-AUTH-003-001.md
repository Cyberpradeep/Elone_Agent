---
type: Playbook
sop_id: SOP-AUTH-003-001
title: How to Reset a User's Password (Admin-Assisted)
category: logins
target_os: 'null'
description: This playbook automates the process for an L1 admin to reset a user's
  password directly via the L1 Support Platform when self-service options are unavailable.
  It involves searching for the user by email and then performing an admin-assisted
  password reset.
knowledge_base_ref: []
required_entities:
- email
trigger_words:
- reset password
- admin reset
- password issue
- locked out
steps:
- step_number: 1
  sop_step_description: Search for the user account by email in the L1 Support Platform
    to confirm the correct user before proceeding with any changes.
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
  sop_step_description: Perform an admin-assisted password reset for the identified
    user, setting a temporary password directly.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: admin_reset_password
  comm_inputs:
    user_id: '{{variables.user_id}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.user_found == 'true'
  timeout_seconds: 30
---

# How to Reset a User's Password (Admin-Assisted) Playbook

## Overview
This playbook automates the process for an L1 admin to reset a user's password directly via the L1 Support Platform when self-service options are unavailable. It involves searching for the user by email and then performing an admin-assisted password reset.

## Execution Steps
- **Step 1**: Search for the user account by email in the L1 Support Platform to confirm the correct user before proceeding with any changes. [Platform: `mock` | Tool Call: `l1_testing_platform_api.search_users({"email": "{{entities.email}}"})`]
- **Step 2**: Perform an admin-assisted password reset for the identified user, setting a temporary password directly. [Platform: `mock` | Tool Call: `l1_testing_platform_api.admin_reset_password({"user_id": "{{variables.user_id}}"})`]
