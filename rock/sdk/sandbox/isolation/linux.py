"""
Linux bubblewrap (bwrap) isolation provider.

Uses bubblewrap to provide namespace-based isolation on Linux.
This provides strong isolation using Linux namespaces (user, mount, network, etc.)
"""

import platform
import shlex
import shutil
from typing import Any

from rock.sdk.sandbox.isolation.base import AbstractIsolationProvider, IsolationConfig


class BubblewrapIsolation(AbstractIsolationProvider):
    """Linux bubblewrap (bwrap) based isolation.

    Uses Linux namespaces to provide:
    - Mount namespace isolation
    - Network namespace isolation (optional)
    - User namespace isolation
    - PID namespace isolation

    Requires bubblewrap (bwrap) to be installed:
    - Ubuntu/Debian: apt install bubblewrap
    - RHEL/CentOS: yum install bubblewrap
    - Arch: pacman -S bubblewrap
    """

    def __init__(self, config: IsolationConfig | None = None):
        super().__init__(config)

    @classmethod
    def is_available(cls) -> bool:
        """Check if bubblewrap is available (Linux only)."""
        return platform.system() == "Linux" and shutil.which("bwrap") is not None

    def _build_bwrap_args(self) -> list[str]:
        """Build bubblewrap command arguments.

        Returns:
            List of bwrap arguments.
        """
        args = ["bwrap"]

        # Basic filesystem setup
        args.extend([
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--symlink", "/usr/lib64", "/lib64",
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--tmpfs", "/run",
        ])

        # Handle /lib64 if it exists
        # args.extend(["--ro-bind-try", "/lib64", "/lib64"])

        # etc files needed for basic operation
        args.extend([
            "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
            "--ro-bind", "/etc/hosts", "/etc/hosts",
            "--ro-bind", "/etc/passwd", "/etc/passwd",
            "--ro-bind", "/etc/group", "/etc/group",
            "--ro-bind-try", "/etc/ssl", "/etc/ssl",
            "--ro-bind-try", "/etc/ca-certificates", "/etc/ca-certificates",
            "--ro-bind-try", "/etc/pki", "/etc/pki",
        ])

        # Read paths
        for path in self._config.allow_read_paths:
            if path not in ["/usr", "/bin", "/lib", "/lib64", "/"]:
                args.extend(["--ro-bind-try", path, path])

        # Write paths
        for path in self._config.allow_write_paths:
            args.extend(["--bind", path, path])

        # Working directory
        if self._config.working_dir:
            wd = str(self._config.working_dir)
            args.extend([
                "--bind", wd, wd,
                "--chdir", wd,
            ])

        # Network isolation
        if not self._config.allow_network:
            args.append("--unshare-net")

        # Additional namespace isolation
        args.extend([
            "--unshare-pid",
            "--die-with-parent",
        ])

        return args

    def wrap_command(self, command: str) -> str:
        """Wrap command with bubblewrap."""
        bwrap_args = self._build_bwrap_args()
        bwrap_args.extend(["/bin/bash", "-c", command])
        return shlex.join(bwrap_args)

    def get_shell_command(self) -> str:
        """Get bubblewrap wrapped shell command."""
        bwrap_args = self._build_bwrap_args()
        bwrap_args.append("/bin/bash")
        return shlex.join(bwrap_args)

    def get_isolation_info(self) -> dict[str, Any]:
        """Return isolation info."""
        return {
            "type": "bubblewrap",
            "available": self.is_available(),
            "platform": "Linux",
            "description": "Linux bubblewrap namespace isolation",
            "allow_network": self._config.allow_network,
            "allow_read_paths": self._config.allow_read_paths,
            "allow_write_paths": self._config.allow_write_paths,
            "features": [
                "mount namespace",
                "pid namespace",
                "network namespace" if not self._config.allow_network else "shared network",
            ],
        }
