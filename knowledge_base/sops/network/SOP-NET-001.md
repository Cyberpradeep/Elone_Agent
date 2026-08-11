---
type: Playbook
sop_id: SOP-NET-001
title: L1 Network Connectivity Troubleshooting via Command Line
category: network
target_os: windows
description: Automated playbook for diagnosing and resolving Windows network connectivity
  issues using CLI tools. Covers DHCP, local TCP/IP stack, gateway reachability, external
  connectivity, and DNS resolution. Escalates to L2 with diagnostic data if unresolved.
required_entities:
- hostname
trigger_words:
- internet
- wifi
- network
- connectivity
- dhcp
- ping
- dns
steps:
- step_number: 1
  sop_step_description: Verify local IP configuration and detect DHCP failure (169.254.x.x
    address).
  step_type: command
  command: ipconfig /all
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: IPv4 Address
  timeout_seconds: 30
  output_variable: ipconfig_output
  output_parse_instruction: Inspect output. If IPv4 Address starts with 169.254.x.x,
    set 'dhcp_failure' to 'true'. Extract Default Gateway IPv4 address into variable
    'default_gateway_ip'. Record active adapter name (Ethernet/Wi-Fi) into variable
    'active_adapter'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 2
  sop_step_description: Release, renew, and flush network settings to resolve DHCP
    lease issues.
  step_type: command
  command: ipconfig /release && ipconfig /renew && ipconfig /flushdns
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Successfully flushed the DNS Resolver Cache
  timeout_seconds: 90
  output_variable: renew_flush_output
  output_parse_instruction: Inspect output of 'ipconfig /renew'. If IPv4 Address still
    starts with 169.254.x.x, set 'dhcp_renewal_failure' to 'true'.
  execute_if: variables.dhcp_failure == 'true'
  is_dangerous: false
  danger_warning: Network connection will drop temporarily during release/renew.
- step_number: 3
  sop_step_description: Test local TCP/IP stack functionality (loopback ping).
  step_type: command
  command: ping 127.0.0.1
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Reply from 127.0.0.1
  timeout_seconds: 30
  output_variable: ping_loopback_output
  output_parse_instruction: Count replies. If fewer than 4 replies, set 'local_stack_failure'
    to 'true'.
  execute_if: null
  is_dangerous: false
  danger_warning: null
- step_number: 4
  sop_step_description: Test connectivity to the default gateway.
  step_type: command
  command: ping {variables.default_gateway_ip}
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Reply from {variables.default_gateway_ip}
  timeout_seconds: 30
  output_variable: ping_gateway_output
  output_parse_instruction: Count replies. If fewer than 4 replies, set 'gateway_connectivity_failure'
    to 'true'.
  execute_if: variables.local_stack_failure != 'true' && variables.default_gateway_ip
    != null
  is_dangerous: false
  danger_warning: null
- step_number: 5
  sop_step_description: Test external internet connectivity (ping 8.8.8.8).
  step_type: command
  command: ping 8.8.8.8
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Reply from 8.8.8.8
  timeout_seconds: 30
  output_variable: ping_external_output
  output_parse_instruction: Count replies. If fewer than 4 replies, set 'external_connectivity_failure'
    to 'true'.
  execute_if: variables.local_stack_failure != 'true' && variables.gateway_connectivity_failure
    != 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 6
  sop_step_description: Trace the network path to 8.8.8.8 to isolate upstream failures.
  step_type: command
  command: tracert 8.8.8.8
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Tracing route to 8.8.8.8
  timeout_seconds: 90
  output_variable: tracert_output
  output_parse_instruction: Inspect hops. If first 1-2 hops show 'Request timed out',
    set 'local_gateway_failure' to 'true'. If later hops time out, set 'upstream_failure'
    to 'true'.
  execute_if: variables.external_connectivity_failure == 'true' && variables.local_stack_failure
    != 'true' && variables.gateway_connectivity_failure != 'true'
  is_dangerous: false
  danger_warning: null
- step_number: 7
  sop_step_description: Confirm DNS name resolution (nslookup www.google.com).
  step_type: command
  command: nslookup www.google.com
  shell: powershell
  fallback_command: null
  fallback_sop_id: null
  expected_output_contains: Non-authoritative answer
  timeout_seconds: 30
  output_variable: nslookup_output
  output_parse_instruction: Inspect output. If 'DNS request timed out' or 'Can't find
    www.google.com', set 'dns_resolution_failure' to 'true'.
  execute_if: variables.local_stack_failure != 'true' && variables.gateway_connectivity_failure
    != 'true' && variables.external_connectivity_failure != 'true'
  is_dangerous: false
  danger_warning: null
---

# L1 Network Connectivity Troubleshooting via Command Line Playbook

## Overview
Automated playbook for diagnosing and resolving Windows network connectivity issues using CLI tools. Covers DHCP, local TCP/IP stack, gateway reachability, external connectivity, and DNS resolution. Escalates to L2 with diagnostic data if unresolved.

## Execution Steps
- **Step 1**: Verify local IP configuration and detect DHCP failure (169.254.x.x address). (`ipconfig /all`)
- **Step 2**: Release, renew, and flush network settings to resolve DHCP lease issues. (`ipconfig /release && ipconfig /renew && ipconfig /flushdns`)
- **Step 3**: Test local TCP/IP stack functionality (loopback ping). (`ping 127.0.0.1`)
- **Step 4**: Test connectivity to the default gateway. (`ping {variables.default_gateway_ip}`)
- **Step 5**: Test external internet connectivity (ping 8.8.8.8). (`ping 8.8.8.8`)
- **Step 6**: Trace the network path to 8.8.8.8 to isolate upstream failures. (`tracert 8.8.8.8`)
- **Step 7**: Confirm DNS name resolution (nslookup www.google.com). (`nslookup www.google.com`)
