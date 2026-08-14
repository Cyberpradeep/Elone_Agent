---
type: Playbook
sop_id: SOP-airretailer-vpn-rdp-001
title: AirRetailer VPN and Remote Desktop Connection Setup
category: network
target_os: windows | mac
description: This playbook automates the process of connecting to the AirRetailer
  VPN and then establishing a Remote Desktop session to an office PC, including client
  installation and configuration based on the user's personal laptop OS.
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
- office_pc_password
- personal_laptop_os
trigger_words:
- vpn
- remote desktop
- airretailer
- connect to office pc
steps:
- step_number: 1
  sop_step_description: Open the AirRetailer VPN sign-in website.
  step_type: tool_call
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
- step_number: 2
  sop_step_description: Derive the VPN username from the user's full name using the
    company rule (first name + first letter of last name).
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: derive_vpn_username
  comm_inputs:
    full_name: '{{entities.full_name}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_portal_opened == 'true'
  timeout_seconds: 30
- step_number: 3
  sop_step_description: Log in to the VPN portal using the derived username and the
    provided password 'Dubai@2025'.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: login_vpn_portal
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: Dubai@2025
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_username_derived == 'true'
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Download the Cisco AnyConnect installer file from the portal,
    specific to the personal laptop's operating system.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: download_vpn_client
  comm_inputs:
    os: '{{entities.personal_laptop_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_portal_login_status == 'true'
  timeout_seconds: 90
- step_number: 5
  sop_step_description: Install the downloaded Cisco AnyConnect client on the personal
    laptop.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: install_vpn_client
  comm_inputs:
    installer_path: '{{variables.vpn_installer_path}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_download_status == 'true'
  timeout_seconds: 300
- step_number: 6
  sop_step_description: Launch the Cisco AnyConnect Secure Mobility Client application.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_vpn_client
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_install_status == 'true'
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Open the settings panel within the Cisco AnyConnect client.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: open_vpn_client_settings
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_launched == 'true'
  timeout_seconds: 30
- step_number: 8
  sop_step_description: Apply the specified Cisco AnyConnect client preferences as
    per the SOP screenshot.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: apply_vpn_client_settings
  comm_inputs:
    preferences:
      Start VPN when AnyConnect is started: false
      Minimize AnyConnect on VPN connect: true
      Allow local (LAN) access when using VPN (if configured): false
      Disable Captive Portal Detection: false
      Block connections to untrusted servers: false
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_settings_opened == 'true'
  timeout_seconds: 30
- step_number: 9
  sop_step_description: Set the VPN server address in the AnyConnect client to 'securevpn.airretailer.com'.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: set_vpn_server_address
  comm_inputs:
    server_url: securevpn.airretailer.com
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_launched == 'true'
  timeout_seconds: 30
- step_number: 10
  sop_step_description: Connect to the VPN using the configured server address and
    user credentials, automatically accepting any security warnings ('Connect Anyway').
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_vpn
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: Dubai@2025
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_server_address_set == 'true'
  timeout_seconds: 90
- step_number: 11
  sop_step_description: Retrieve the local IP address of the office PC.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: get_office_pc_ip
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_connection_status == 'true'
  timeout_seconds: 30
- step_number: 12
  sop_step_description: Install the Microsoft Remote Desktop app if the personal laptop's
    OS is Mac, as it's mainly needed on Mac.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: install_remote_desktop_app
  comm_inputs:
    os: '{{entities.personal_laptop_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: entities.personal_laptop_os == 'mac' && variables.office_pc_ip_address_retrieved
    == 'true'
  timeout_seconds: 300
- step_number: 13
  sop_step_description: Launch the Microsoft Remote Desktop application on the personal
    laptop.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_remote_desktop_app
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.office_pc_ip_address_retrieved == 'true'
  timeout_seconds: 30
- step_number: 14
  sop_step_description: Save the office PC in the remote desktop app by entering its
    network address (IP address).
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: add_remote_pc
  comm_inputs:
    ip_address: '{{variables.office_pc_ip}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.rdp_app_launched == 'true'
  timeout_seconds: 30
- step_number: 15
  sop_step_description: Retrieve the login username used on the office PC.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: get_office_pc_username
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.remote_pc_added == 'true'
  timeout_seconds: 30
- step_number: 16
  sop_step_description: Format the office PC username into the correct shape for the
    personal laptop's operating system (Windows or Mac).
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: format_remote_login
  comm_inputs:
    username: '{{variables.office_pc_username}}'
    os: '{{entities.personal_laptop_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.office_pc_username_details == 'true'
  timeout_seconds: 30
- step_number: 17
  sop_step_description: Start the remote desktop session using the saved PC, formatted
    login details, and the office PC password.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_remote_pc
  comm_inputs:
    pc_id: '{{variables.remote_pc_id}}'
    formatted_username: '{{variables.formatted_rdp_username}}'
    password: '{{entities.office_pc_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.formatted_rdp_username == 'true'
  timeout_seconds: 90
---

# AirRetailer VPN and Remote Desktop Connection Setup Playbook

## Overview
This playbook automates the process of connecting to the AirRetailer VPN and then establishing a Remote Desktop session to an office PC, including client installation and configuration based on the user's personal laptop OS.

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
- **Step 1**: Open the AirRetailer VPN sign-in website. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_portal({})`]
- **Step 2**: Derive the VPN username from the user's full name using the company rule (first name + first letter of last name). [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.derive_vpn_username({"full_name": "{{entities.full_name}}"})`]
- **Step 3**: Log in to the VPN portal using the derived username and the provided password 'Dubai@2025'. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.login_vpn_portal({"username": "{{variables.vpn_username}}", "password": "Dubai@2025"})`]
- **Step 4**: Download the Cisco AnyConnect installer file from the portal, specific to the personal laptop's operating system. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.download_vpn_client({"os": "{{entities.personal_laptop_os}}"})`]
- **Step 5**: Install the downloaded Cisco AnyConnect client on the personal laptop. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_vpn_client({"installer_path": "{{variables.vpn_installer_path}}"})`]
- **Step 6**: Launch the Cisco AnyConnect Secure Mobility Client application. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_vpn_client({})`]
- **Step 7**: Open the settings panel within the Cisco AnyConnect client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_client_settings({})`]
- **Step 8**: Apply the specified Cisco AnyConnect client preferences as per the SOP screenshot. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.apply_vpn_client_settings({"preferences": {"Start VPN when AnyConnect is started": false, "Minimize AnyConnect on VPN connect": true, "Allow local (LAN) access when using VPN (if configured)": false, "Disable Captive Portal Detection": false, "Block connections to untrusted servers": false}})`]
- **Step 9**: Set the VPN server address in the AnyConnect client to 'securevpn.airretailer.com'. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.set_vpn_server_address({"server_url": "securevpn.airretailer.com"})`]
- **Step 10**: Connect to the VPN using the configured server address and user credentials, automatically accepting any security warnings ('Connect Anyway'). [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_vpn({"username": "{{variables.vpn_username}}", "password": "Dubai@2025"})`]
- **Step 11**: Retrieve the local IP address of the office PC. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.get_office_pc_ip({})`]
- **Step 12**: Install the Microsoft Remote Desktop app if the personal laptop's OS is Mac, as it's mainly needed on Mac. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_remote_desktop_app({"os": "{{entities.personal_laptop_os}}"})`]
- **Step 13**: Launch the Microsoft Remote Desktop application on the personal laptop. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_remote_desktop_app({})`]
- **Step 14**: Save the office PC in the remote desktop app by entering its network address (IP address). [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.add_remote_pc({"ip_address": "{{variables.office_pc_ip}}"})`]
- **Step 15**: Retrieve the login username used on the office PC. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.get_office_pc_username({})`]
- **Step 16**: Format the office PC username into the correct shape for the personal laptop's operating system (Windows or Mac). [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.format_remote_login({"username": "{{variables.office_pc_username}}", "os": "{{entities.personal_laptop_os}}"})`]
- **Step 17**: Start the remote desktop session using the saved PC, formatted login details, and the office PC password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_remote_pc({"pc_id": "{{variables.remote_pc_id}}", "formatted_username": "{{variables.formatted_rdp_username}}", "password": "{{entities.office_pc_password}}"})`]
