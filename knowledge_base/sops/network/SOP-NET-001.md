---
type: Playbook
sop_id: SOP-NET-001
title: L1 Network Connectivity Troubleshooting via Command Prompt
category: network
target_os: windows
description: This playbook provides a step-by-step procedure for L1 Helpdesk technicians
  to diagnose, isolate, and resolve a user's inability to connect to the internet
  or internal company network resources using native Windows command-line tools. It
  covers wired and Wi-Fi connectivity issues on Windows 10/11 workstations where the
  OS boots normally and a command prompt is accessible with elevated privileges.
knowledge_base_ref: []
required_entities: []
trigger_words:
- network
- connectivity
- internet
- troubleshooting
- ipconfig
- ping
- tracert
- nslookup
- no internet
- cannot connect
steps:
- step_number: 1
  sop_step_description: Verify Local IP Configuration by running 'ipconfig /all' to
    identify the active network adapter, its IPv4 Address, Subnet Mask, and Default
    Gateway. This step also checks for a 169.254.x.x address or a disconnected adapter.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ipconfig /all
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Release the current IP address configuration.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ipconfig /release
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_starts_with_169 == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Renew the IP address configuration and check if a valid IP
    is obtained (not 169.254.x.x).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ipconfig /renew
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_starts_with_169 == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Flush the DNS resolver cache to clear any stale DNS entries.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ipconfig /flushdns
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_starts_with_169 == 'true'
  timeout_seconds: 30
- step_number: 5
  sop_step_description: Test the local TCP/IP stack by pinging the loopback address
    (127.0.0.1).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ping 127.0.0.1
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.no_adapter_connected != 'true' && (variables.ipv4_address_starts_with_169
    != 'true' || (variables.ipv4_address_starts_with_169 == 'true' && variables.renew_still_169
    != 'true'))
  timeout_seconds: 30
- step_number: 6
  sop_step_description: Test connectivity to the local gateway using the Default Gateway
    IP obtained in Step 1.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ping {{variables.default_gateway_ip}}
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_loopback_failed != 'true'
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Test external public internet connectivity by pinging 8.8.8.8
    (Google's DNS server).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ping 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_gateway_failed != 'true'
  timeout_seconds: 30
- step_number: 8
  sop_step_description: Trace the network path to 8.8.8.8 to isolate where the connection
    is failing, if external ping failed.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: tracert 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_loopback_failed != 'true' && variables.ping_gateway_failed
    != 'true' && variables.ping_external_failed == 'true'
  timeout_seconds: 90
- step_number: 9
  sop_step_description: Confirm DNS name resolution by performing an 'nslookup' for
    www.google.com, if basic IP connectivity is restored.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: nslookup www.google.com
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_loopback_failed != 'true' && variables.ping_gateway_failed
    != 'true' && variables.ping_external_failed != 'true'
  timeout_seconds: 30
---

# L1 Network Connectivity Troubleshooting via Command Prompt Playbook

## Overview
This playbook provides a step-by-step procedure for L1 Helpdesk technicians to diagnose, isolate, and resolve a user's inability to connect to the internet or internal company network resources using native Windows command-line tools. It covers wired and Wi-Fi connectivity issues on Windows 10/11 workstations where the OS boots normally and a command prompt is accessible with elevated privileges.

## Execution Steps
- **Step 1**: Verify Local IP Configuration by running 'ipconfig /all' to identify the active network adapter, its IPv4 Address, Subnet Mask, and Default Gateway. This step also checks for a 169.254.x.x address or a disconnected adapter. (`ipconfig /all`)
- **Step 2**: Release the current IP address configuration. (`ipconfig /release`)
- **Step 3**: Renew the IP address configuration and check if a valid IP is obtained (not 169.254.x.x). (`ipconfig /renew`)
- **Step 4**: Flush the DNS resolver cache to clear any stale DNS entries. (`ipconfig /flushdns`)
- **Step 5**: Test the local TCP/IP stack by pinging the loopback address (127.0.0.1). (`ping 127.0.0.1`)
- **Step 6**: Test connectivity to the local gateway using the Default Gateway IP obtained in Step 1. (`ping {{variables.default_gateway_ip}}`)
- **Step 7**: Test external public internet connectivity by pinging 8.8.8.8 (Google's DNS server). (`ping 8.8.8.8`)
- **Step 8**: Trace the network path to 8.8.8.8 to isolate where the connection is failing, if external ping failed. (`tracert 8.8.8.8`)
- **Step 9**: Confirm DNS name resolution by performing an 'nslookup' for www.google.com, if basic IP connectivity is restored. (`nslookup www.google.com`)
