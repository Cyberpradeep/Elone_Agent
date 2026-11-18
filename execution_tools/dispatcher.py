"""Universal OS Driver Dispatcher (WinRM for Windows, SSH for Linux, Local Fast-Path)."""

from typing import Any, Dict
from .winrm_executor import run_remote_command as run_winrm_command
from .ssh_executor import run_remote_ssh_command


def dispatch_remote_command(
    hostname: str,
    command: str,
    shell: str = "powershell",
    target_os: str = "windows",
    username: str = None,
    password: str = None,
    timeout_seconds: int = 90,
    elevated: bool = False,
    port: int = None,
) -> Dict[str, Any]:
    """Dynamically routes command execution based on target OS and shell type.

    - Windows targets (or PowerShell/CMD shells) route to WinRM (Port 5985).
    - Linux targets (or Bash/Sh shells) route to Paramiko SSH (Port 22).
    - Local targets (localhost, 127.0.0.1, local computername) run via fast-path subprocess.
    """
    clean_os = str(target_os or "").lower().strip()
    clean_shell = str(shell or "").lower().strip()

    is_linux = "linux" in clean_os or clean_shell in ("bash", "sh", "zsh")

    if is_linux:
        ssh_port = port or 22
        return run_remote_ssh_command(
            hostname=hostname,
            command=command,
            shell=shell,
            username=username,
            password=password,
            timeout_seconds=timeout_seconds,
            elevated=elevated,
            port=ssh_port,
        )
    else:
        # Default to WinRM for Windows and PowerShell/CMD commands
        return run_winrm_command(
            hostname=hostname,
            command=command,
            shell=shell,
            username=username,
            password=password,
            timeout_seconds=timeout_seconds,
            elevated=elevated,
        )

