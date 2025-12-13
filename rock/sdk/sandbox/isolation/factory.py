"""
Factory for creating isolation providers.
"""

import platform
from typing import Literal

from rock.logger import init_logger
from rock.sdk.sandbox.isolation.base import AbstractIsolationProvider, IsolationConfig
from rock.sdk.sandbox.isolation.linux import BubblewrapIsolation
from rock.sdk.sandbox.isolation.macos import SandboxExecIsolation
from rock.sdk.sandbox.isolation.none import NoIsolation

logger = init_logger(__name__)

IsolationMode = Literal["none", "sandbox-exec", "bubblewrap", "auto"]


class IsolationProviderFactory:
    """Factory for creating isolation providers based on mode and platform."""

    _providers: dict[str, type[AbstractIsolationProvider]] = {
        "none": NoIsolation,
        "sandbox-exec": SandboxExecIsolation,
        "bubblewrap": BubblewrapIsolation,
    }

    @classmethod
    def create(
        cls,
        mode: IsolationMode = "auto",
        config: IsolationConfig | None = None,
    ) -> AbstractIsolationProvider:
        """Create an isolation provider.

        Args:
            mode: Isolation mode - "none", "sandbox-exec", "bubblewrap", or "auto".
            config: Configuration for the isolation provider.

        Returns:
            An instance of AbstractIsolationProvider.

        Raises:
            ValueError: If the requested isolation mode is not available.
        """
        if mode == "auto":
            return cls._create_auto(config)

        provider_class = cls._providers.get(mode)
        if provider_class is None:
            raise ValueError(f"Unknown isolation mode: {mode}")

        if not provider_class.is_available():
            raise ValueError(
                f"Isolation mode '{mode}' is not available on this system. "
                f"Platform: {platform.system()}"
            )

        return provider_class(config)

    @classmethod
    def _create_auto(cls, config: IsolationConfig | None = None) -> AbstractIsolationProvider:
        """Auto-detect and create the best available isolation provider.

        Priority:
        1. Platform-native isolation (sandbox-exec on macOS, bubblewrap on Linux)
        2. NoIsolation as fallback

        Args:
            config: Configuration for the isolation provider.

        Returns:
            An instance of the best available isolation provider.
        """
        system = platform.system()

        if system == "Darwin":
            if SandboxExecIsolation.is_available():
                logger.info("Auto-selected sandbox-exec isolation for macOS")
                return SandboxExecIsolation(config)
            else:
                logger.warning("sandbox-exec not available, falling back to no isolation")

        elif system == "Linux":
            if BubblewrapIsolation.is_available():
                logger.info("Auto-selected bubblewrap isolation for Linux")
                return BubblewrapIsolation(config)
            else:
                logger.warning(
                    "bubblewrap not available, falling back to no isolation. "
                    "Install with: apt install bubblewrap (Debian/Ubuntu) or "
                    "yum install bubblewrap (RHEL/CentOS)"
                )

        else:
            logger.warning(f"No isolation available for platform: {system}")

        return NoIsolation(config)

    @classmethod
    def list_available(cls) -> dict[str, bool]:
        """List all isolation modes and their availability.

        Returns:
            Dictionary mapping mode names to availability status.
        """
        return {
            mode: provider.is_available()
            for mode, provider in cls._providers.items()
        }

    @classmethod
    def get_recommended(cls) -> str:
        """Get the recommended isolation mode for the current platform.

        Returns:
            The recommended isolation mode name.
        """
        system = platform.system()

        if system == "Darwin" and SandboxExecIsolation.is_available():
            return "sandbox-exec"
        elif system == "Linux" and BubblewrapIsolation.is_available():
            return "bubblewrap"
        else:
            return "none"
