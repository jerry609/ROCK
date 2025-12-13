"""
No isolation provider - direct execution without any sandboxing.

This is the fastest option and suitable for:
- Local development and testing
- Trusted code execution
- Environments where isolation is handled externally (e.g., containers)
"""

from typing import Any

from rock.sdk.sandbox.isolation.base import AbstractIsolationProvider, IsolationConfig


class NoIsolation(AbstractIsolationProvider):
    """No isolation - commands are executed directly without sandboxing.

    This provider passes commands through unchanged, providing no security
    isolation but maximum compatibility and performance.
    """

    def __init__(self, config: IsolationConfig | None = None):
        super().__init__(config)

    @classmethod
    def is_available(cls) -> bool:
        """NoIsolation is always available."""
        return True

    def wrap_command(self, command: str) -> str:
        """Return command unchanged."""
        return command

    def get_shell_command(self) -> str:
        """Return standard bash shell command."""
        return "/bin/bash"

    def get_isolation_info(self) -> dict[str, Any]:
        """Return isolation info."""
        return {
            "type": "none",
            "available": True,
            "description": "No isolation - direct execution",
        }
