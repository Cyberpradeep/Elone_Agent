---
type: Playbook
sop_id: SOP-AirRetailer-VPN-RDP-001
title: AirRetailer VPN and Remote Desktop Setup
category: network
target_os: windows
description: This playbook automates the process of setting up AirRetailer VPN using
  Cisco AnyConnect and then establishing a Remote Desktop connection to an office
  PC.
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
- vpn_password
- remote_pc_username
- remote_pc_password
- target_os
trigger_words:
- vpn
- remote desktop
- anyconnect
- airretailer
steps:
- step_number: 1
  sop_step_description: Open the AirRetailer VPN portal.
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
  sop_step_description: Derive the VPN username from the full name.
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
  sop_step_description: Log in to the VPN portal with the derived username and provided
    password.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: login_vpn_portal
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: '{{entities.vpn_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_username != null
  timeout_seconds: 30
- step_number: 4
  sop_step_description: Download the Cisco AnyConnect client installer.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: download_vpn_client
  comm_inputs:
    os: '{{entities.target_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_login_status == 'true'
  timeout_seconds: 90
- step_number: 5
  sop_step_description: Install the Cisco AnyConnect client.
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
  execute_if: variables.vpn_installer_path != null
  timeout_seconds: 90
- step_number: 6
  sop_step_description: Launch the Cisco AnyConnect Secure Mobility Client.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_vpn_client
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_client_installed == 'true'
  timeout_seconds: 30
- step_number: 7
  sop_step_description: Open the settings panel within the AnyConnect client.
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
  sop_step_description: Configure the remote server URL in AnyConnect settings.
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
  execute_if: variables.vpn_settings_opened == 'true'
  timeout_seconds: 30
- step_number: 9
  sop_step_description: Connect to the VPN using the configured server and user credentials.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_vpn
  comm_inputs:
    username: '{{variables.vpn_username}}'
    password: '{{entities.vpn_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_server_address_set == 'true'
  timeout_seconds: 90
- step_number: 10
  sop_step_description: Find the local PC's IP address using ipconfig.
  step_type: command
  platform: null
  provider: null
  function_name: null
  comm_inputs: {}
  command: ipconfig /all
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.vpn_connected_status == 'true'
  timeout_seconds: 30
- step_number: 11
  sop_step_description: Launch the Microsoft Remote Desktop application.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: launch_remote_desktop_app
  comm_inputs: {}
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.local_pc_ip != null
  timeout_seconds: 30
- step_number: 12
  sop_step_description: Add the remote PC to the Remote Desktop application using
    its IP address.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: add_remote_pc
  comm_inputs:
    ip_address: '{{variables.local_pc_ip}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.rdp_app_launched == 'true'
  timeout_seconds: 30
- step_number: 13
  sop_step_description: Format the remote PC username based on the target OS.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: format_remote_login
  comm_inputs:
    username: '{{entities.remote_pc_username}}'
    os: '{{entities.target_os}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.remote_pc_added != null
  timeout_seconds: 30
- step_number: 14
  sop_step_description: Connect to the remote PC using Remote Desktop with the formatted
    username and password.
  step_type: tool_call
  platform: airretailer
  provider: airretailer_vpn_rdp_tools
  function_name: connect_remote_pc
  comm_inputs:
    pc_id: '{{variables.remote_pc_id}}'
    formatted_username: '{{variables.formatted_remote_username}}'
    password: '{{entities.remote_pc_password}}'
  command: null
  fallback_command: null
  fallback_sop_id: null
  parse_instruction: null
  execute_if: variables.formatted_remote_username != null
  timeout_seconds: 90
---

# AirRetailer VPN and Remote Desktop Setup Playbook

## Overview
This playbook automates the process of setting up AirRetailer VPN using Cisco AnyConnect and then establishing a Remote Desktop connection to an office PC.

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
- **Step 1**: Open the AirRetailer VPN portal. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_portal({})`]
- **Step 2**: Derive the VPN username from the full name. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.derive_vpn_username({"full_name": "{{entities.full_name}}"})`]
- **Step 3**: Log in to the VPN portal with the derived username and provided password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.login_vpn_portal({"username": "{{variables.vpn_username}}", "password": "{{entities.vpn_password}}"})`]
- **Step 4**: Download the Cisco AnyConnect client installer. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.download_vpn_client({"os": "{{entities.target_os}}"})`]
- **Step 5**: Install the Cisco AnyConnect client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.install_vpn_client({"installer_path": "{{variables.vpn_installer_path}}"})`]
- **Step 6**: Launch the Cisco AnyConnect Secure Mobility Client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_vpn_client({})`]
- **Step 7**: Open the settings panel within the AnyConnect client. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.open_vpn_client_settings({})`]
- **Step 8**: Configure the remote server URL in AnyConnect settings. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.set_vpn_server_address({"server_url": "securevpn.airretailer.com"})`]
- **Step 9**: Connect to the VPN using the configured server and user credentials. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_vpn({"username": "{{variables.vpn_username}}", "password": "{{entities.vpn_password}}"})`]
- **Step 10**: Find the local PC's IP address using ipconfig. (`ipconfig /all`)
- **Step 11**: Launch the Microsoft Remote Desktop application. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.launch_remote_desktop_app({})`]
- **Step 12**: Add the remote PC to the Remote Desktop application using its IP address. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.add_remote_pc({"ip_address": "{{variables.local_pc_ip}}"})`]
- **Step 13**: Format the remote PC username based on the target OS. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.format_remote_login({"username": "{{entities.remote_pc_username}}", "os": "{{entities.target_os}}"})`]
- **Step 14**: Connect to the remote PC using Remote Desktop with the formatted username and password. [Platform: `airretailer` | Tool Call: `airretailer_vpn_rdp_tools.connect_remote_pc({"pc_id": "{{variables.remote_pc_id}}", "formatted_username": "{{variables.formatted_remote_username}}", "password": "{{entities.remote_pc_password}}"})`]
