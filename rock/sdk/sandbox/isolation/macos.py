"""
macOS sandbox-exec isolation provider.

Uses macOS's built-in sandbox-exec command to provide syscall-level filtering.
This provides moderate isolation with low performance overhead.
"""

import platform
import shlex
import shutil
from typing import Any

from rock.sdk.sandbox.isolation.base import AbstractIsolationProvider, IsolationConfig


class SandboxExecIsolation(AbstractIsolationProvider):
    """macOS sandbox-exec based isolation.

    Uses the sandbox-exec command with a custom profile to restrict:
    - File system access (read/write paths)
    - Network access
    - Process operations

    Note: sandbox-exec is deprecated by Apple but still functional.
    """

    def __init__(self, config: IsolationConfig | None = None):
        super().__init__(config)
        self._profile: str | None = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if sandbox-exec is available (macOS only)."""
        return platform.system() == "Darwin" and shutil.which("sandbox-exec") is not None

    def _generate_profile(self) -> str:
        """Generate sandbox-exec profile based on configuration.

        Returns:
            Scheme-like sandbox profile string.
        """
        lines = [
            "(version 1)",
            "(deny default)",
            # Basic process operations
            "(allow process-fork)",
            "(allow process-exec)",
            "(allow signal)",
            # File operations
            "(allow file-read-metadata)",
            "(allow file-read-xattr)",
        ]

        # Read paths
        for path in self._config.allow_read_paths:
            escaped_path = path.replace('"', '\\"')
            lines.append(f'(allow file-read* (subpath "{escaped_path}"))')

        # Write paths
        for path in self._config.allow_write_paths:
            escaped_path = path.replace('"', '\\"')
            lines.append(f'(allow file-write* (subpath "{escaped_path}"))')

        # Always allow /tmp and /var for basic operations
        lines.extend([
            '(allow file-read* (subpath "/tmp"))',
            '(allow file-write* (subpath "/tmp"))',
            '(allow file-read* (subpath "/private/tmp"))',
            '(allow file-write* (subpath "/private/tmp"))',
            '(allow file-read* (subpath "/var"))',
            '(allow file-write* (subpath "/var/folders"))',
            '(allow file-read* (subpath "/dev"))',
            '(allow file-write* (subpath "/dev/null"))',
            '(allow file-write* (subpath "/dev/tty"))',
        ])

        # Network access
        if self._config.allow_network:
            lines.extend([
                "(allow network*)",
                "(allow system-socket)",
            ])

        # System operations needed for bash
        lines.extend([
            "(allow sysctl-read)",
            "(allow mach-lookup)",
            "(allow ipc-posix-shm-read-data)",
            "(allow ipc-posix-shm-write-data)",
        ])

        return "\n".join(lines)

    @property
    def profile(self) -> str:
        """Get or generate the sandbox profile."""
        if self._profile is None:
            self._profile = self._generate_profile()
        return self._profile

    def wrap_command(self, command: str) -> str:
        """Wrap command with sandbox-exec."""
        profile = self.profile
        # Escape single quotes in command
        escaped_command = command.replace("'", "'\"'\"'")
        escaped_profile = profile.replace("'", "'\"'\"'")
        return f"sandbox-exec -p '{escaped_profile}' /bin/bash -c '{escaped_command}'"

    def get_shell_command(self) -> str:
        """Get sandbox-exec wrapped shell command."""
        profile = self.profile
        escaped_profile = profile.replace("'", "'\"'\"'")
        return f"sandbox-exec -p '{escaped_profile}' /bin/bash"

    def get_isolation_info(self) -> dict[str, Any]:
        """Return isolation info."""
        return {
            "type": "sandbox-exec",
            "available": self.is_available(),
            "platform": "macOS",
            "description": "macOS sandbox-exec syscall filtering",
            "allow_network": self._config.allow_network,
            "allow_read_paths": self._config.allow_read_paths,
            "allow_write_paths": self._config.allow_write_paths,
        }
