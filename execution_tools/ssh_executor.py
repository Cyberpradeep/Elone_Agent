import os
import re
import socket
import subprocess
import tempfile
import uuid
from typing import Any, Dict
# pyrefly: ignore [missing-import]
import paramiko


def resolve_remote_target(hostname: str) -> str:
    """Attempts to resolve target hostname to IP or mDNS (.local) if standard resolution fails."""
    if not hostname or hostname in ("localhost", "127.0.0.1"):
        return hostname

    # 1. Check if already an IP address
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", hostname):
        return hostname

    # 2. Try standard socket DNS resolution
    try:
        socket.gethostbyname(hostname)
        return hostname
    except Exception:
        pass

    # 3. Fallback to mDNS (.local) for local network laptops
    try:
        mdns_name = f"{hostname.rstrip('.')}.local"
        socket.gethostbyname(mdns_name)
        return mdns_name
    except Exception:
        pass

    return hostname


def run_remote_ssh_command(
    hostname: str,
    command: str,
    shell: str = "powershell",
    username: str = None,
    password: str = None,
    timeout_seconds: int = 90,
    elevated: bool = False,
    port: int = 22,
) -> Dict[str, Any]:
    """Executes a shell command on a target machine over SSH via Paramiko.

    Dynamically handles local machine direct execution or remote SSH execution.
    Auto-detects elevated commands and manages connection lifecycles cleanly.
    """
    if not hostname or not isinstance(hostname, str):
        hostname = "localhost"
    if not command or not isinstance(command, str):
        command = ""

    host_lower = hostname.lower()
    local_comp_name = os.environ.get("COMPUTERNAME", "").lower()

    try:
        local_host = socket.gethostname().lower()
        local_fqdn = socket.getfqdn().lower()
        local_ip = socket.gethostbyname(local_host)
    except Exception:
        local_host = local_fqdn = local_ip = ""

    local_identifiers = {
        "localhost", "127.0.0.1", "::1", "target_machine",
        local_comp_name, local_host, local_fqdn, local_ip
    }
    local_identifiers.discard("")

    is_local = host_lower in local_identifiers

    # Elevated command detection
    elevated_keywords = {"chkdsk", "sfc", "dism", "diskpart", "netsh", "gpupdate"}
    cmd_first_word = command.strip().split()[0].lower() if command.strip() else ""
    is_elevated_cmd = elevated or (cmd_first_word in elevated_keywords)

    # Local execution fast-path
    if is_local:
        try:
            if shell == "powershell":
                cmd_list = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command]
            else:
                cmd_list = ["cmd.exe", "/c", command]

            completed = subprocess.run(
                cmd_list,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )

            stdout = completed.stdout.strip()
            stderr = completed.stderr.strip()
            exit_code = completed.returncode

            # Local elevated scheduled task retry fallback
            if exit_code in (3, 5) or "access is denied" in stderr.lower() or "privileges" in stderr.lower():
                if is_elevated_cmd:
                    task_name = f"L1Agent_Elevated_{uuid.uuid4().hex[:8]}"
                    temp_out = os.path.join(tempfile.gettempdir(), f"{task_name}.log")

                    elevated_ps = (
                        f'$TaskName = "{task_name}"; '
                        f'$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c {command} > {temp_out} 2>&1"; '
                        f'Register-ScheduledTask -TaskName $TaskName -Action $Action -User "NT AUTHORITY\\SYSTEM" -RunLevel Highest -Force | Out-Null; '
                        f'Start-ScheduledTask -TaskName $TaskName; '
                        f'Start-Sleep -Seconds 3; '
                        f'if (Test-Path "{temp_out}") {{ Get-Content "{temp_out}" -Raw }}; '
                        f'Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null; '
                        f'if (Test-Path "{temp_out}") {{ Remove-Item "{temp_out}" -Force | Out-Null }}'
                    )

                    elev_run = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", elevated_ps],
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds + 10,
                    )

                    if elev_run.returncode == 0 and elev_run.stdout.strip():
                        stdout = elev_run.stdout.strip()
                        stderr = ""
                        exit_code = 0

            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "command": command,
                "hostname": hostname,
                "protocol": "local",
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"[Local Process Error]: {str(e)}",
                "command": command,
                "hostname": hostname,
                "error": str(e),
                "protocol": "local",
            }

    # Remote Paramiko SSH execution path
    resolved_target = resolve_remote_target(hostname)
    user = username or os.environ.get("SSH_USERNAME", "Administrator")
    pwd = password or os.environ.get("SSH_PASSWORD", "Password123!")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=resolved_target,
            port=port,
            username=user,
            password=pwd,
            timeout=timeout_seconds,
            banner_timeout=timeout_seconds,
        )

        shell = "powershell" if not shell or shell.lower() == "cmd" else shell
        if shell == "powershell":
            escaped_cmd = command.replace('"', '\\"')
            remote_cmd = f'powershell.exe -NoProfile -NonInteractive -Command "{escaped_cmd}"'
        else:
            escaped_cmd = command.replace('"', '""')
            remote_cmd = f'cmd.exe /c "{escaped_cmd}"'

        stdin, stdout_stream, stderr_stream = client.exec_command(remote_cmd, timeout=timeout_seconds)

        exit_code = stdout_stream.channel.recv_exit_status()
        stdout = stdout_stream.read().decode("utf-8", errors="replace").strip()
        stderr = stderr_stream.read().decode("utf-8", errors="replace").strip()

        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "command": command,
            "hostname": hostname,
            "protocol": "ssh",
        }
    except Exception as e:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": f"[Paramiko SSH Error]: {str(e)}",
            "command": command,
            "hostname": hostname,
            "error": str(e),
            "protocol": "ssh",
        }
    finally:
        client.close()
