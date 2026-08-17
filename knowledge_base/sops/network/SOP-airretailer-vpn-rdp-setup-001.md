---
type: Playbook
sop_id: SOP-airretailer-vpn-rdp-setup-001
title: AirRetailer VPN and Remote Desktop Setup Playbook
category: network
target_os: windows
description: This playbook automates the setup of AirRetailer VPN using Cisco AnyConnect
  and establishes a remote desktop connection to an office PC. It covers deriving
  the VPN username, logging into the VPN portal, downloading and installing the VPN
  client, configuring VPN settings, connecting to VPN, collecting the local IP address,
  and setting up a remote desktop session.
knowledge_base_ref:
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_1.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_1_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_2.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_2_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_3.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_3_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_4.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_4_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_5.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_5_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_6.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_6_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_7.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_7_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_8.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_8_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_9.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_9_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_10.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_10_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_11.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_11_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_12.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_12_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_13.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_13_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_14.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_14_report.json
- image_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_15.png
  file_path: knowledge_base/logs/images/AR-VPN-DETAILS-1/img_15_report.json
required_entities:
- full_name
- password
- server_url
- os
trigger_words:
- VPN
- Cisco AnyConnect
- Remote Desktop
- RDP
- AirRetailer
steps:
- step_number: 1
  sop_step_description: Derive VPN username from the user's full name using the company
    rule (first name + first letter of last name).
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP explicitly mentions deriving the VPN username
    from the user''s full name. The ''derive_vpn_username'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this requirement. The required input ''full_name'' is provided
    as an entity.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: derive_vpn_username
  comm_inputs:
    full_name: '{{entities.full_name}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 2
  sop_step_description: Open the VPN portal in a web browser.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs opening the VPN portal. The
    ''open_vpn_portal'' function from the ''airretailer_vpn_rdp_tools'' platform matches
    this action. No required inputs are needed.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: open_vpn_portal
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Log in to the VPN portal using the derived username and provided
    password.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes logging into the VPN portal.
    The ''login_vpn_portal'' function from the ''airretailer_vpn_rdp_tools'' platform
    matches this action. Required inputs ''username'' and ''password'' are provided
    as variables and entities.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: login_vpn_portal
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: '{{entities.password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Download the Cisco AnyConnect Secure Mobility Client installer
    for the specified OS.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs downloading the Cisco AnyConnect
    client. The ''download_vpn_client'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. The required input ''os'' is provided as an entity.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: download_vpn_client
  comm_inputs:
    os: '{{entities.os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 300
- step_number: 5
  sop_step_description: Install the Cisco AnyConnect Secure Mobility Client using
    the downloaded installer.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes installing the Cisco AnyConnect
    client. The ''install_vpn_client'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. The required input ''installer_path'' is provided
    as a variable from the previous step.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: install_vpn_client
  comm_inputs:
    installer_path: '{{variables.vpn_installer_path}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 300
- step_number: 6
  sop_step_description: Launch the Cisco AnyConnect Secure Mobility Client.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs launching the Cisco AnyConnect
    client. The ''launch_vpn_client'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. No required inputs are needed.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_vpn_client
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Open the settings panel in the Cisco AnyConnect client.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes opening the settings panel in
    the Cisco AnyConnect client. The ''open_vpn_client_settings'' function from the
    ''airretailer_vpn_rdp_tools'' platform matches this action. No required inputs
    are needed.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: open_vpn_client_settings
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 8
  sop_step_description: Apply the VPN client settings as specified in the SOP.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes applying specific settings in
    the Cisco AnyConnect client. The ''apply_vpn_client_settings'' function from the
    ''airretailer_vpn_rdp_tools'' platform matches this action. The required input
    ''preferences'' is inferred from the SOP.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: apply_vpn_client_settings
  comm_inputs:
    preferences:
      block_untrusted_servers: false
      auto_reconnect: true
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 9
  sop_step_description: Set the VPN server address in the Cisco AnyConnect client.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs setting the VPN server address.
    The ''set_vpn_server_address'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. The required input ''server_url'' is provided as
    an entity.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: set_vpn_server_address
  comm_inputs:
    server_url: '{{entities.server_url}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 10
  sop_step_description: Connect to the VPN using the derived username and provided
    password.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes connecting to the VPN. The ''connect_vpn''
    function from the ''airretailer_vpn_rdp_tools'' platform matches this action.
    Required inputs ''username'' and ''password'' are provided as variables and entities.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_vpn
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: '{{entities.password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 90
- step_number: 11
  sop_step_description: Collect the local IP address of the office PC.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs collecting the local IP address.
    The ''get_office_pc_ip'' function from the ''airretailer_vpn_rdp_tools'' platform
    matches this action. No required inputs are needed.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: get_office_pc_ip
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_connected.connected == true
  timeout_seconds: 30
- step_number: 12
  sop_step_description: Launch the Microsoft Remote Desktop application on the personal
    laptop.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs launching the Microsoft Remote
    Desktop application. The ''launch_remote_desktop_app'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. No required inputs are needed.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_remote_desktop_app
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_connected.connected == true
  timeout_seconds: 30
- step_number: 13
  sop_step_description: Add the office PC to the Microsoft Remote Desktop application
    using its local IP address.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes adding the office PC to the
    Remote Desktop application. The ''add_remote_pc'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. The required input ''ip_address'' is provided as
    a variable from the previous step.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: add_remote_pc
  comm_inputs:
    ip_address: '{{variables.office_pc_ip}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.rdp_app_launched.app_open == true
  timeout_seconds: 30
- step_number: 14
  sop_step_description: Format the office PC username for the specified OS.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes formatting the office PC username.
    The ''format_remote_login'' function from the ''airretailer_vpn_rdp_tools'' platform
    matches this action. Required inputs ''username'' and ''os'' are provided as variables
    and entities.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: format_remote_login
  comm_inputs:
    username: '{{variables.vpn_username}}'
    os: '{{entities.os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.remote_pc_id != null
  timeout_seconds: 30
- step_number: 15
  sop_step_description: Connect to the office PC using the Microsoft Remote Desktop
    application with the formatted username and provided password.
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP describes connecting to the office PC
    via Remote Desktop. The ''connect_remote_pc'' function from the ''airretailer_vpn_rdp_tools''
    platform matches this action. Required inputs ''pc_id'', ''formatted_username'',
    and ''password'' are provided as variables and entities.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_remote_pc
  comm_inputs:
    pc_id: '{{variables.remote_pc_id}}'
    formatted_username: '{{variables.formatted_remote_username}}'
    password: '{{entities.password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.formatted_remote_username != null
  timeout_seconds: 90
---

# AirRetailer VPN and Remote Desktop Setup Playbook Playbook

## Overview
This playbook automates the setup of AirRetailer VPN using Cisco AnyConnect and establishes a remote desktop connection to an office PC. It covers deriving the VPN username, logging into the VPN portal, downloading and installing the VPN client, configuring VPN settings, connecting to VPN, collecting the local IP address, and setting up a remote desktop session.

## Knowledge Base References
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_1.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_1_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_2.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_2_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_3.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_3_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_4.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_4_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_5.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_5_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_6.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_6_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_7.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_7_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_8.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_8_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_9.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_9_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_10.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_10_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_11.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_11_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_12.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_12_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_13.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_13_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_14.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_14_report.json`
- Image Screenshot: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_15.png` — Visual Audit Metadata: `knowledge_base/logs/images/AR-VPN-DETAILS-1/img_15_report.json`

## Execution Steps
- **Step 1**: Derive VPN username from the user's full name using the company rule (first name + first letter of last name). [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.derive_vpn_username({"full_name": "{{entities.full_name}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP explicitly mentions deriving the VPN username from the user's full name. The 'derive_vpn_username' function from the 'airretailer_vpn_rdp_tools' platform matches this requirement. The required input 'full_name' is provided as an entity.
- **Step 2**: Open the VPN portal in a web browser. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_portal({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs opening the VPN portal. The 'open_vpn_portal' function from the 'airretailer_vpn_rdp_tools' platform matches this action. No required inputs are needed.
- **Step 3**: Log in to the VPN portal using the derived username and provided password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.login_vpn_portal({"username": "{{variables.vpn_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes logging into the VPN portal. The 'login_vpn_portal' function from the 'airretailer_vpn_rdp_tools' platform matches this action. Required inputs 'username' and 'password' are provided as variables and entities.
- **Step 4**: Download the Cisco AnyConnect Secure Mobility Client installer for the specified OS. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.download_vpn_client({"os": "{{entities.os}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs downloading the Cisco AnyConnect client. The 'download_vpn_client' function from the 'airretailer_vpn_rdp_tools' platform matches this action. The required input 'os' is provided as an entity.
- **Step 5**: Install the Cisco AnyConnect Secure Mobility Client using the downloaded installer. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_vpn_client({"installer_path": "{{variables.vpn_installer_path}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes installing the Cisco AnyConnect client. The 'install_vpn_client' function from the 'airretailer_vpn_rdp_tools' platform matches this action. The required input 'installer_path' is provided as a variable from the previous step.
- **Step 6**: Launch the Cisco AnyConnect Secure Mobility Client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_vpn_client({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs launching the Cisco AnyConnect client. The 'launch_vpn_client' function from the 'airretailer_vpn_rdp_tools' platform matches this action. No required inputs are needed.
- **Step 7**: Open the settings panel in the Cisco AnyConnect client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_client_settings({})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes opening the settings panel in the Cisco AnyConnect client. The 'open_vpn_client_settings' function from the 'airretailer_vpn_rdp_tools' platform matches this action. No required inputs are needed.
- **Step 8**: Apply the VPN client settings as specified in the SOP. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.apply_vpn_client_settings({"preferences": {"block_untrusted_servers": false, "auto_reconnect": true}})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes applying specific settings in the Cisco AnyConnect client. The 'apply_vpn_client_settings' function from the 'airretailer_vpn_rdp_tools' platform matches this action. The required input 'preferences' is inferred from the SOP.
- **Step 9**: Set the VPN server address in the Cisco AnyConnect client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.set_vpn_server_address({"server_url": "{{entities.server_url}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs setting the VPN server address. The 'set_vpn_server_address' function from the 'airretailer_vpn_rdp_tools' platform matches this action. The required input 'server_url' is provided as an entity.
- **Step 10**: Connect to the VPN using the derived username and provided password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_vpn({"username": "{{variables.vpn_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes connecting to the VPN. The 'connect_vpn' function from the 'airretailer_vpn_rdp_tools' platform matches this action. Required inputs 'username' and 'password' are provided as variables and entities.
- **Step 11**: Collect the local IP address of the office PC. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.get_office_pc_ip({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs collecting the local IP address. The 'get_office_pc_ip' function from the 'airretailer_vpn_rdp_tools' platform matches this action. No required inputs are needed.
- **Step 12**: Launch the Microsoft Remote Desktop application on the personal laptop. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_remote_desktop_app({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs launching the Microsoft Remote Desktop application. The 'launch_remote_desktop_app' function from the 'airretailer_vpn_rdp_tools' platform matches this action. No required inputs are needed.
- **Step 13**: Add the office PC to the Microsoft Remote Desktop application using its local IP address. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.add_remote_pc({"ip_address": "{{variables.office_pc_ip}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes adding the office PC to the Remote Desktop application. The 'add_remote_pc' function from the 'airretailer_vpn_rdp_tools' platform matches this action. The required input 'ip_address' is provided as a variable from the previous step.
- **Step 14**: Format the office PC username for the specified OS. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.format_remote_login({"username": "{{variables.vpn_username}}", "os": "{{entities.os}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes formatting the office PC username. The 'format_remote_login' function from the 'airretailer_vpn_rdp_tools' platform matches this action. Required inputs 'username' and 'os' are provided as variables and entities.
- **Step 15**: Connect to the office PC using the Microsoft Remote Desktop application with the formatted username and provided password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_remote_pc({"pc_id": "{{variables.remote_pc_id}}", "formatted_username": "{{variables.formatted_remote_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP describes connecting to the office PC via Remote Desktop. The 'connect_remote_pc' function from the 'airretailer_vpn_rdp_tools' platform matches this action. Required inputs 'pc_id', 'formatted_username', and 'password' are provided as variables and entities.
