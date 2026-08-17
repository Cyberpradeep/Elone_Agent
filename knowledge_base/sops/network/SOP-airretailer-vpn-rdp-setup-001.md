---
type: Playbook
sop_id: SOP-airretailer-vpn-rdp-setup-001
title: AirRetailer VPN and Remote Desktop Setup Playbook
category: network
target_os: windows
description: Automates the setup of AirRetailer VPN using Cisco AnyConnect and establishes
  a Remote Desktop connection to an office PC. Steps include deriving VPN username,
  logging into the VPN portal, installing the VPN client, configuring settings, connecting
  to VPN, retrieving office PC IP, and initiating RDP.
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
trigger_words:
- vpn
- remote desktop
- cisco anyconnect
- rdp
steps:
- step_number: 1
  sop_step_description: Derive VPN username from full name using company rule (first
    name + first letter of last name)
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies deriving VPN username from full
    name, which matches the ''derive_vpn_username'' function in the ''airretailer_vpn_rdp_tools''
    provider. The provider is active, solves the exact problem, and requires ''full_name''
    as input, which is available as an entity.'
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
  sop_step_description: Open the VPN sign-in website in a browser
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs to open the VPN portal, which
    matches the ''open_vpn_portal'' function in the ''airretailer_vpn_rdp_tools''
    provider. The provider is active, solves the exact problem, and requires no inputs.'
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
  sop_step_description: Sign in to the VPN website with derived username and password
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies logging into the VPN portal,
    which matches the ''login_vpn_portal'' function. The provider is active, solves
    the exact problem, and requires ''username'' and ''password'' inputs, which are
    available from entities and prior step output.'
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
  sop_step_description: Download the Cisco AnyConnect installer for the current OS
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs to download the VPN client,
    which matches the ''download_vpn_client'' function. The provider is active, solves
    the exact problem, and requires ''os'' input, which can be inferred from the target_os
    field.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: download_vpn_client
  comm_inputs:
    os: '{{target_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 90
- step_number: 5
  sop_step_description: Install the downloaded Cisco AnyConnect client
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies installing the VPN client, which
    matches the ''install_vpn_client'' function. The provider is active, solves the
    exact problem, and requires ''installer_path'' input, which is available from
    the prior step output.'
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
  sop_step_description: Launch the installed Cisco AnyConnect app
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP instructs to open the VPN client, which
    matches the ''launch_vpn_client'' function. The provider is active, solves the
    exact problem, and requires no inputs.'
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
  sop_step_description: Open the settings panel inside the AnyConnect app
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies opening settings, which matches
    the ''open_vpn_client_settings'' function. The provider is active, solves the
    exact problem, and requires no inputs.'
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
  sop_step_description: Set the VPN server address to securevpn.airretailer.com
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies configuring the VPN server URL,
    which matches the ''set_vpn_server_address'' function. The provider is active,
    solves the exact problem, and requires ''server_url'' input, which is explicitly
    provided in the SOP.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: set_vpn_server_address
  comm_inputs:
    server_url: securevpn.airretailer.com
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 9
  sop_step_description: Start the VPN connection with derived username and password,
    auto-accepting security warnings
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies connecting to VPN, which matches
    the ''connect_vpn'' function. The provider is active, solves the exact problem,
    and requires ''username'' and ''password'' inputs, which are available from entities
    and prior step output.'
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
- step_number: 10
  sop_step_description: Retrieve the office PC's local network IP address
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies finding the office PC''s IP,
    which matches the ''get_office_pc_ip'' function. The provider is active, solves
    the exact problem, and requires no inputs.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: get_office_pc_ip
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 11
  sop_step_description: Look up the login username for the office PC
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies finding the office PC username,
    which matches the ''get_office_pc_username'' function. The provider is active,
    solves the exact problem, and requires no inputs.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: get_office_pc_username
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 12
  sop_step_description: 'Format the office PC username for the target OS (Windows:
    airretailer.local\username, Mac: username@airretailer.local)'
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies formatting the username for
    the OS, which matches the ''format_remote_login'' function. The provider is active,
    solves the exact problem, and requires ''username'' and ''os'' inputs, which are
    available from prior step output and the target_os field.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: format_remote_login
  comm_inputs:
    username: '{{variables.office_pc_username}}'
    os: '{{target_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 13
  sop_step_description: Install Microsoft Remote Desktop app (if on Mac)
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies installing RDP app for Mac,
    which matches the ''install_remote_desktop_app'' function. The provider is active,
    solves the exact problem, and requires ''os'' input, which is available from the
    target_os field. This step is conditional on target_os being ''mac''.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: install_remote_desktop_app
  comm_inputs:
    os: '{{target_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: target_os == 'mac'
  timeout_seconds: 300
- step_number: 14
  sop_step_description: Launch the Microsoft Remote Desktop app
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies opening the RDP app, which matches
    the ''launch_remote_desktop_app'' function. The provider is active, solves the
    exact problem, and requires no inputs.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_remote_desktop_app
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 15
  sop_step_description: Save the office PC in the Remote Desktop app using its IP
    address
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies adding the office PC to RDP,
    which matches the ''add_remote_pc'' function. The provider is active, solves the
    exact problem, and requires ''ip_address'' input, which is available from prior
    step output.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: add_remote_pc
  comm_inputs:
    ip_address: '{{variables.office_pc_ip}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 30
- step_number: 16
  sop_step_description: Start the Remote Desktop session using the saved PC and login
    details
  step_type: tool_call
  step_reasoning: 'Gate 1-4 passed: The SOP specifies connecting via RDP, which matches
    the ''connect_remote_pc'' function. The provider is active, solves the exact problem,
    and requires ''pc_id'', ''formatted_username'', and ''password'' inputs, which
    are available from entities and prior step outputs.'
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_remote_pc
  comm_inputs:
    pc_id: '{{variables.remote_pc_id}}'
    formatted_username: '{{variables.formatted_office_pc_username}}'
    password: '{{entities.password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: null
  timeout_seconds: 90
---

# AirRetailer VPN and Remote Desktop Setup Playbook Playbook

## Overview
Automates the setup of AirRetailer VPN using Cisco AnyConnect and establishes a Remote Desktop connection to an office PC. Steps include deriving VPN username, logging into the VPN portal, installing the VPN client, configuring settings, connecting to VPN, retrieving office PC IP, and initiating RDP.

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
- **Step 1**: Derive VPN username from full name using company rule (first name + first letter of last name) [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.derive_vpn_username({"full_name": "{{entities.full_name}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies deriving VPN username from full name, which matches the 'derive_vpn_username' function in the 'airretailer_vpn_rdp_tools' provider. The provider is active, solves the exact problem, and requires 'full_name' as input, which is available as an entity.
- **Step 2**: Open the VPN sign-in website in a browser [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_portal({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs to open the VPN portal, which matches the 'open_vpn_portal' function in the 'airretailer_vpn_rdp_tools' provider. The provider is active, solves the exact problem, and requires no inputs.
- **Step 3**: Sign in to the VPN website with derived username and password [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.login_vpn_portal({"username": "{{variables.vpn_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies logging into the VPN portal, which matches the 'login_vpn_portal' function. The provider is active, solves the exact problem, and requires 'username' and 'password' inputs, which are available from entities and prior step output.
- **Step 4**: Download the Cisco AnyConnect installer for the current OS [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.download_vpn_client({"os": "{{target_os}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs to download the VPN client, which matches the 'download_vpn_client' function. The provider is active, solves the exact problem, and requires 'os' input, which can be inferred from the target_os field.
- **Step 5**: Install the downloaded Cisco AnyConnect client [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_vpn_client({"installer_path": "{{variables.vpn_installer_path}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies installing the VPN client, which matches the 'install_vpn_client' function. The provider is active, solves the exact problem, and requires 'installer_path' input, which is available from the prior step output.
- **Step 6**: Launch the installed Cisco AnyConnect app [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_vpn_client({})`]
  - *Why this output:* Gate 1-4 passed: The SOP instructs to open the VPN client, which matches the 'launch_vpn_client' function. The provider is active, solves the exact problem, and requires no inputs.
- **Step 7**: Open the settings panel inside the AnyConnect app [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_client_settings({})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies opening settings, which matches the 'open_vpn_client_settings' function. The provider is active, solves the exact problem, and requires no inputs.
- **Step 8**: Set the VPN server address to securevpn.airretailer.com [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.set_vpn_server_address({"server_url": "securevpn.airretailer.com"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies configuring the VPN server URL, which matches the 'set_vpn_server_address' function. The provider is active, solves the exact problem, and requires 'server_url' input, which is explicitly provided in the SOP.
- **Step 9**: Start the VPN connection with derived username and password, auto-accepting security warnings [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_vpn({"username": "{{variables.vpn_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies connecting to VPN, which matches the 'connect_vpn' function. The provider is active, solves the exact problem, and requires 'username' and 'password' inputs, which are available from entities and prior step output.
- **Step 10**: Retrieve the office PC's local network IP address [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.get_office_pc_ip({})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies finding the office PC's IP, which matches the 'get_office_pc_ip' function. The provider is active, solves the exact problem, and requires no inputs.
- **Step 11**: Look up the login username for the office PC [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.get_office_pc_username({})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies finding the office PC username, which matches the 'get_office_pc_username' function. The provider is active, solves the exact problem, and requires no inputs.
- **Step 12**: Format the office PC username for the target OS (Windows: airretailer.local\username, Mac: username@airretailer.local) [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.format_remote_login({"username": "{{variables.office_pc_username}}", "os": "{{target_os}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies formatting the username for the OS, which matches the 'format_remote_login' function. The provider is active, solves the exact problem, and requires 'username' and 'os' inputs, which are available from prior step output and the target_os field.
- **Step 13**: Install Microsoft Remote Desktop app (if on Mac) [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_remote_desktop_app({"os": "{{target_os}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies installing RDP app for Mac, which matches the 'install_remote_desktop_app' function. The provider is active, solves the exact problem, and requires 'os' input, which is available from the target_os field. This step is conditional on target_os being 'mac'.
- **Step 14**: Launch the Microsoft Remote Desktop app [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_remote_desktop_app({})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies opening the RDP app, which matches the 'launch_remote_desktop_app' function. The provider is active, solves the exact problem, and requires no inputs.
- **Step 15**: Save the office PC in the Remote Desktop app using its IP address [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.add_remote_pc({"ip_address": "{{variables.office_pc_ip}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies adding the office PC to RDP, which matches the 'add_remote_pc' function. The provider is active, solves the exact problem, and requires 'ip_address' input, which is available from prior step output.
- **Step 16**: Start the Remote Desktop session using the saved PC and login details [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_remote_pc({"pc_id": "{{variables.remote_pc_id}}", "formatted_username": "{{variables.formatted_office_pc_username}}", "password": "{{entities.password}}"})`]
  - *Why this output:* Gate 1-4 passed: The SOP specifies connecting via RDP, which matches the 'connect_remote_pc' function. The provider is active, solves the exact problem, and requires 'pc_id', 'formatted_username', and 'password' inputs, which are available from entities and prior step outputs.
