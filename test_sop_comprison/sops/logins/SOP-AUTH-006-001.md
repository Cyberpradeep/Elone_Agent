---
type: Playbook
sop_id: SOP-AUTH-006-001
title: Disable MFA for a User
category: logins
target_os: null
description: This playbook disables Multi-Factor Authentication (MFA) for a user after
  confirming their current password, as requested by the user or admin.
knowledge_base_ref: []
required_entities:
- user_id
- current_password
trigger_words:
- disable MFA
- turn off MFA
- MFA disable
steps:
- step_number: 1
  sop_step_description: Disable MFA for the user after confirming their current password.
  step_type: tool_call
  platform: mock
  provider: l1_testing_platform_api
  function_name: disable_mfa
  comm_inputs:
    user_id: '{{entities.user_id}}'
    current_password: '{{entities.current_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
---

# Disable MFA for a User Playbook

## Overview
This playbook disables Multi-Factor Authentication (MFA) for a user after confirming their current password, as requested by the user or admin.

## Execution Steps
- **Step 1**: Disable MFA for the user after confirming their current password. [Platform: `mock` | Tool Call: `l1_testing_platform_api.disable_mfa({"user_id": "{{entities.user_id}}", "current_password": "{{entities.current_password}}"})`]
