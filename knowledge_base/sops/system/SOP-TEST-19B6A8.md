---
type: Playbook
sop_id: SOP-TEST-19B6A8
title: Flush System Diagnostics
platform: system
category: system
target_os: windows
description: Diagnostic and cache flush playbook.
confidence_score: 0.95
confidence_level: High
confidence_reason: Deterministic test mock
required_entities:
- email
trigger_words:
- flush
- diagnostics
steps:
- step_number: 1
  description: Test connectivity
  action: run_command
  step_type: command
  command: ping 127.0.0.1
  source_text_quote: 'Step 1: Test connectivity'
- step_number: 2
  description: Flush caches and restart
  action: run_command
  step_type: command
  command: ipconfig /flushdns
  source_text_quote: 'Step 2: Flush caches and restart'
integrity_version: v2
integrity_hmac_sha256: 546c399b25a2d17944279fc58c07e129152d72d70baae8b6263490e9cd8e07b8
---

# Flush System Diagnostics Playbook

## Overview
Diagnostic and cache flush playbook.

## Execution Steps
- **Step 1**: None (`ping 127.0.0.1`)
- **Step 2**: None (`ipconfig /flushdns`)
