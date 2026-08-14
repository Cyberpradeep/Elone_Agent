---
type: Playbook
sop_id: SOP-NET-001
title: L1 Network Connectivity Troubleshooting via Command Prompt
category: network
target_os: windows
description: This playbook provides a step-by-step procedure to diagnose, isolate,
  and resolve a user's inability to connect to the internet or internal company network
  resources using native Windows command-line tools. It covers wired and Wi-Fi connectivity
  issues on Windows 10/11 workstations where the OS boots normally and the user can
  reach a command prompt.
knowledge_base_ref: []
required_entities:
- hostname
trigger_words:
- network
- connectivity
- internet
- troubleshooting
- ipconfig
- ping
- tracert
- nslookup
steps:
- step_number: 1
  sop_step_description: Verify Local IP Configuration by running `ipconfig /all` and
    extracting IPv4 Address, Subnet Mask, and Default Gateway. This step also determines
    if the adapter failed to obtain a DHCP lease (APIPA address) or if DHCP is working.
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
  sop_step_description: Release the current IP address if an APIPA address was detected,
    indicating a DHCP lease failure.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /release
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_apipa == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Renew the IP address if an APIPA address was detected. Check
    if the renewed address still starts with 169.254.x.x.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /renew
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_apipa == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Flush the DNS Resolver Cache after renewing the IP address,
    if an APIPA address was initially detected.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /flushdns
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.is_apipa == 'true'
  timeout_seconds: 30
- step_number: 5
  sop_step_description: Test the local TCP/IP stack by pinging the loopback address
    (127.0.0.1). This is a fundamental check for network stack integrity.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping 127.0.0.1
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.dhcp_working == 'true' || variables.renew_failed_apipa ==
    'false'
  timeout_seconds: 30
- step_number: 6
  sop_step_description: Test connectivity to the local gateway by pinging its IP address,
    which was recorded in Step 1.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping {{variables.default_gateway_ip}}
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.loopback_ping_success == 'true' && variables.default_gateway_ip
    != '0.0.0.0'
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Test external public internet connectivity by pinging a reliable
    public DNS server (8.8.8.8).
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ping 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.gateway_ping_success == 'true'
  timeout_seconds: 30
- step_number: 8
  sop_step_description: Trace the network path to 8.8.8.8 to isolate routing issues,
    only if local and gateway pings succeeded but external ping failed.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: tracert 8.8.8.8
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.loopback_ping_success == 'true' && variables.gateway_ping_success
    == 'true' && variables.external_ping_success == 'false'
  timeout_seconds: 90
- step_number: 9
  sop_step_description: Confirm DNS name resolution by performing an nslookup for
    www.google.com, only if all ping tests in Step 4 fully succeeded.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: nslookup www.google.com
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.loopback_ping_success == 'true' && variables.gateway_ping_success
    == 'true' && variables.external_ping_success == 'true'
  timeout_seconds: 30
- step_number: 10
  sop_step_description: Re-run `ipconfig /flushdns` if DNS resolution failed in the
    previous step, as a specific remediation for DNS issues.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: null
  command: ipconfig /flushdns
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.dns_resolution_failure == 'true'
  timeout_seconds: 30
---

# L1 Network Connectivity Troubleshooting via Command Prompt Playbook

## Overview
This playbook provides a step-by-step procedure to diagnose, isolate, and resolve a user's inability to connect to the internet or internal company network resources using native Windows command-line tools. It covers wired and Wi-Fi connectivity issues on Windows 10/11 workstations where the OS boots normally and the user can reach a command prompt.

## Execution Steps
- **Step 1**: Verify Local IP Configuration by running `ipconfig /all` and extracting IPv4 Address, Subnet Mask, and Default Gateway. This step also determines if the adapter failed to obtain a DHCP lease (APIPA address) or if DHCP is working. (`ipconfig /all`)
- **Step 2**: Release the current IP address if an APIPA address was detected, indicating a DHCP lease failure. (`ipconfig /release`)
- **Step 3**: Renew the IP address if an APIPA address was detected. Check if the renewed address still starts with 169.254.x.x. (`ipconfig /renew`)
- **Step 4**: Flush the DNS Resolver Cache after renewing the IP address, if an APIPA address was initially detected. (`ipconfig /flushdns`)
- **Step 5**: Test the local TCP/IP stack by pinging the loopback address (127.0.0.1). This is a fundamental check for network stack integrity. (`ping 127.0.0.1`)
- **Step 6**: Test connectivity to the local gateway by pinging its IP address, which was recorded in Step 1. (`ping {{variables.default_gateway_ip}}`)
- **Step 7**: Test external public internet connectivity by pinging a reliable public DNS server (8.8.8.8). (`ping 8.8.8.8`)
- **Step 8**: Trace the network path to 8.8.8.8 to isolate routing issues, only if local and gateway pings succeeded but external ping failed. (`tracert 8.8.8.8`)
- **Step 9**: Confirm DNS name resolution by performing an nslookup for www.google.com, only if all ping tests in Step 4 fully succeeded. (`nslookup www.google.com`)
- **Step 10**: Re-run `ipconfig /flushdns` if DNS resolution failed in the previous step, as a specific remediation for DNS issues. (`ipconfig /flushdns`)
