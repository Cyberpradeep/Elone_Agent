import pytest
from unittest.mock import patch
from execution_tools.dispatcher import dispatch_remote_command


def test_windows_target_routes_to_winrm():
    with patch("execution_tools.dispatcher.run_winrm_command") as mock_winrm:
        mock_winrm.return_value = {
            "success": True,
            "exit_code": 0,
            "stdout": "WinRM output",
            "stderr": "",
            "protocol": "winrm"
        }
        res = dispatch_remote_command(
            hostname="192.168.1.100",
            command="Get-Process",
            shell="powershell",
            target_os="windows"
        )
        assert mock_winrm.called
        assert res["stdout"] == "WinRM output"


def test_linux_target_routes_to_ssh():
    with patch("execution_tools.dispatcher.run_remote_ssh_command") as mock_ssh:
        mock_ssh.return_value = {
            "success": True,
            "exit_code": 0,
            "stdout": "SSH output",
            "stderr": "",
            "protocol": "ssh"
        }
        res = dispatch_remote_command(
            hostname="192.168.1.101",
            command="systemctl status nginx",
            shell="bash",
            target_os="linux"
        )
        assert mock_ssh.called
        assert res["stdout"] == "SSH output"


def test_shell_powershell_defaults_to_winrm():
    with patch("execution_tools.dispatcher.run_winrm_command") as mock_winrm:
        mock_winrm.return_value = {"success": True, "exit_code": 0, "stdout": "ok"}
        dispatch_remote_command(
            hostname="server01",
            command="Get-Service",
            shell="powershell",
            target_os=""
        )
        assert mock_winrm.called


def test_shell_bash_defaults_to_ssh():
    with patch("execution_tools.dispatcher.run_remote_ssh_command") as mock_ssh:
        mock_ssh.return_value = {"success": True, "exit_code": 0, "stdout": "ok"}
        dispatch_remote_command(
            hostname="server02",
            command="ls -la",
            shell="bash",
            target_os=""
        )
        assert mock_ssh.called

