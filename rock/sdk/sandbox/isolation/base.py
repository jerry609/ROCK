"""
Abstract base class for isolation providers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class IsolationConfig(BaseModel):
    """Configuration for isolation providers."""

    allow_network: bool = Field(default=True, description="Allow network access")
    allow_read_paths: list[str] = Field(default=["/"], description="Paths allowed for reading")
    allow_write_paths: list[str] = Field(default=[], description="Paths allowed for writing")
    working_dir: Path | None = Field(default=None, description="Working directory for sandbox")
    env_vars: dict[str, str] = Field(default_factory=dict, description="Environment variables")


class AbstractIsolationProvider(ABC):
    """Abstract base class for process isolation mechanisms.

    Isolation providers wrap command execution to add security boundaries.
    Different implementations provide varying levels of isolation:
    - NoIsolation: No isolation, direct execution
    - SandboxExecIsolation: macOS sandbox-exec (syscall filtering)
    - BubblewrapIsolation: Linux bubblewrap (namespace isolation)
    """

    def __init__(self, config: IsolationConfig | None = None):
        self._config = config or IsolationConfig()

    @property
    def config(self) -> IsolationConfig:
        return self._config

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool:
        """Check if this isolation mechanism is available on the current system.

        Returns:
            True if the isolation mechanism can be used, False otherwise.
        """

    @abstractmethod
    def wrap_command(self, command: str) -> str:
        """Wrap a command to execute it within the isolation boundary.

        Args:
            command: The original command to execute.

        Returns:
            The wrapped command with isolation applied.
        """

    @abstractmethod
    def get_shell_command(self) -> str:
        """Get the shell command to spawn an isolated shell session.

        Returns:
            Command string to spawn an isolated /bin/bash session.
        """

    def wrap_session_env(self, env: dict[str, str] | None) -> dict[str, str]:
        """Wrap environment variables for session creation.

        Args:
            env: Original environment variables.

        Returns:
            Modified environment variables with isolation settings.
        """
        result = dict(env) if env else {}
        result.update(self._config.env_vars)
        return result

    @abstractmethod
    def get_isolation_info(self) -> dict[str, Any]:
        """Get information about the current isolation configuration.

        Returns:
            Dictionary with isolation details for debugging/logging.
        """
