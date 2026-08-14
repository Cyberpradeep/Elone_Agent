---
type: Playbook
sop_id: SOP-NET-001
title: L1 Network Connectivity Troubleshooting via Command Prompt
category: network
target_os: windows
description: This playbook provides a step-by-step procedure to diagnose, isolate,
  and resolve a user's inability to connect to the internet or internal company network
  resources using native Windows command-line tools (Windows 10/11). It covers wired
  and Wi-Fi connectivity issues where the OS boots normally and the user can reach
  a command prompt. Local Administrator privileges are assumed for command execution.
knowledge_base_ref: []
required_entities:
- hostname
trigger_words:
- network
- connectivity
- internet
- troubleshooting
- cmd
- ipconfig
- ping
- tracert
- nslookup
steps:
- step_number: 1
  sop_step_description: Verify local IP configuration by running 'ipconfig /all' to
    gather network adapter details.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /all
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Release the current IP address if an APIPA address (169.254.x.x)
    was detected.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /release
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_is_apipa == 'true'
  timeout_seconds: 90
- step_number: 3
  sop_step_description: Renew the IP address after releasing it, if an APIPA address
    was detected.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /renew
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_is_apipa == 'true'
  timeout_seconds: 90
- step_number: 4
  sop_step_description: Flush the DNS resolver cache, if an APIPA address was detected
    and renewed.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /flushdns
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ipv4_address_is_apipa == 'true'
  timeout_seconds: 90
- step_number: 5
  sop_step_description: Test the local TCP/IP stack by pinging the loopback address
    (127.0.0.1).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping 127.0.0.1
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.adapter_connected == 'true' and (variables.ipv4_address_is_apipa
    == 'false' or (variables.ipv4_address_is_apipa == 'true' and variables.renew_ipv4_address_is_apipa
    == 'false'))
  timeout_seconds: 30
- step_number: 6
  sop_step_description: Test connectivity to the local network gateway using the IP
    address recorded in Step 1.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping {{variables.default_gateway_ip}}
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_127_success == 'true' and variables.adapter_connected
    == 'true' and (variables.ipv4_address_is_apipa == 'false' or (variables.ipv4_address_is_apipa
    == 'true' and variables.renew_ipv4_address_is_apipa == 'false'))
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Test external public internet connectivity by pinging 8.8.8.8
    (Google DNS).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_gateway_success == 'true' and variables.adapter_connected
    == 'true' and (variables.ipv4_address_is_apipa == 'false' or (variables.ipv4_address_is_apipa
    == 'true' and variables.renew_ipv4_address_is_apipa == 'false'))
  timeout_seconds: 30
- step_number: 8
  sop_step_description: Trace the network path to 8.8.8.8 to isolate external routing
    issues, if ping to 8.8.8.8 failed but local pings succeeded.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: tracert 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_127_success == 'true' and variables.ping_gateway_success
    == 'true' and variables.ping_8888_success == 'false'
  timeout_seconds: 90
- step_number: 9
  sop_step_description: Confirm DNS name resolution by performing an nslookup for
    www.google.com, if all ping tests succeeded.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: nslookup www.google.com
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.ping_127_success == 'true' and variables.ping_gateway_success
    == 'true' and variables.ping_8888_success == 'true'
  timeout_seconds: 30
- step_number: 10
  sop_step_description: Re-flush DNS resolver cache if nslookup failed after successful
    pings, indicating a DNS-specific issue.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /flushdns
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.nslookup_success == 'false' and variables.ping_127_success
    == 'true' and variables.ping_gateway_success == 'true' and variables.ping_8888_success
    == 'true'
  timeout_seconds: 90
---

# L1 Network Connectivity Troubleshooting via Command Prompt Playbook

## Overview
This playbook provides a step-by-step procedure to diagnose, isolate, and resolve a user's inability to connect to the internet or internal company network resources using native Windows command-line tools (Windows 10/11). It covers wired and Wi-Fi connectivity issues where the OS boots normally and the user can reach a command prompt. Local Administrator privileges are assumed for command execution.

## Execution Steps
- **Step 1**: Verify local IP configuration by running 'ipconfig /all' to gather network adapter details. (`ipconfig /all`)
- **Step 2**: Release the current IP address if an APIPA address (169.254.x.x) was detected. (`ipconfig /release`)
- **Step 3**: Renew the IP address after releasing it, if an APIPA address was detected. (`ipconfig /renew`)
- **Step 4**: Flush the DNS resolver cache, if an APIPA address was detected and renewed. (`ipconfig /flushdns`)
- **Step 5**: Test the local TCP/IP stack by pinging the loopback address (127.0.0.1). (`ping 127.0.0.1`)
- **Step 6**: Test connectivity to the local network gateway using the IP address recorded in Step 1. (`ping {{variables.default_gateway_ip}}`)
- **Step 7**: Test external public internet connectivity by pinging 8.8.8.8 (Google DNS). (`ping 8.8.8.8`)
- **Step 8**: Trace the network path to 8.8.8.8 to isolate external routing issues, if ping to 8.8.8.8 failed but local pings succeeded. (`tracert 8.8.8.8`)
- **Step 9**: Confirm DNS name resolution by performing an nslookup for www.google.com, if all ping tests succeeded. (`nslookup www.google.com`)
- **Step 10**: Re-flush DNS resolver cache if nslookup failed after successful pings, indicating a DNS-specific issue. (`ipconfig /flushdns`)
