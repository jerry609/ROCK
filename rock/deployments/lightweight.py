"""
Lightweight deployment - runs sandbox directly on local machine with optional isolation.

This deployment type provides a simple, no-dependency way to run sandboxes
using only the local system, optionally with platform-native isolation
(sandbox-exec on macOS, bubblewrap on Linux).
"""

from pathlib import Path
from typing import Any, Literal

from typing_extensions import Self

from rock.actions import IsAliveResponse
from rock.deployments.abstract import AbstractDeployment
from rock.deployments.hooks.abstract import CombinedDeploymentHook, DeploymentHook
from rock.logger import init_logger
from rock.rocklet.exceptions import DeploymentNotStartedError
from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig

logger = init_logger(__name__)

__all__ = ["LightweightDeployment", "LightweightDeploymentConfig"]


class LightweightDeploymentConfig:
    """Configuration for lightweight deployment.

    This is a simplified config that wraps LightweightSandboxConfig
    for use with the deployment system.
    """

    def __init__(
        self,
        isolation_mode: Literal["none", "sandbox-exec", "bubblewrap", "auto"] = "auto",
        working_dir: Path | str | None = None,
        env_vars: dict[str, str] | None = None,
        allow_network: bool = True,
        allow_read_paths: list[str] | None = None,
        allow_write_paths: list[str] | None = None,
        **kwargs: Any,
    ):
        self.isolation_mode = isolation_mode
        self.working_dir = Path(working_dir) if working_dir else None
        self.env_vars = env_vars or {}
        self.allow_network = allow_network
        self.allow_read_paths = allow_read_paths or ["/"]
        self.allow_write_paths = allow_write_paths or []

    def to_sandbox_config(self) -> LightweightSandboxConfig:
        """Convert to LightweightSandboxConfig."""
        return LightweightSandboxConfig(
            isolation_mode=self.isolation_mode,
            working_dir=self.working_dir,
            env_vars=self.env_vars,
            allow_network=self.allow_network,
            allow_read_paths=self.allow_read_paths,
            allow_write_paths=self.allow_write_paths,
        )


class LightweightDeployment(AbstractDeployment):
    """Lightweight deployment that runs directly on local machine.

    This deployment wraps LightweightSandbox to provide the same interface
    as other deployment types (Docker, Ray, Remote) but runs without
    any external dependencies.

    Example:
        deployment = LightweightDeployment()
        await deployment.start()

        runtime = deployment.runtime
        await runtime.create_session(CreateBashSessionRequest(session="main"))
        result = await runtime.arun("echo hello", session="main")

        await deployment.stop()
    """

    def __init__(self, **kwargs: Any):
        """Initialize lightweight deployment.

        Args:
            **kwargs: Configuration options (see LightweightDeploymentConfig).
        """
        self._config = LightweightDeploymentConfig(**kwargs)
        self._sandbox: LightweightSandbox | None = None
        self._hooks = CombinedDeploymentHook()

    def add_hook(self, hook: DeploymentHook):
        """Add a deployment hook."""
        self._hooks.add_hook(hook)

    @classmethod
    def from_config(cls, config: LightweightDeploymentConfig) -> Self:
        """Create deployment from config."""
        return cls(
            isolation_mode=config.isolation_mode,
            working_dir=config.working_dir,
            env_vars=config.env_vars,
            allow_network=config.allow_network,
            allow_read_paths=config.allow_read_paths,
            allow_write_paths=config.allow_write_paths,
        )

    async def is_alive(self, *, timeout: float | None = None) -> IsAliveResponse:
        """Check if the deployment is alive.

        Args:
            timeout: Timeout in seconds (unused for lightweight).

        Returns:
            IsAliveResponse indicating status.
        """
        if self._sandbox is None:
            return IsAliveResponse(is_alive=False, message="Sandbox not started")
        return await self._sandbox.is_alive(timeout=timeout)

    async def start(self):
        """Start the deployment."""
        if self._sandbox is not None:
            logger.warning("Deployment already started")
            return

        sandbox_config = self._config.to_sandbox_config()
        self._sandbox = LightweightSandbox(sandbox_config)

        self._hooks.on_custom_step("Starting lightweight sandbox")
        await self._sandbox.start()

        isolation_info = self._sandbox.get_isolation_info()
        logger.info(f"Lightweight deployment started with isolation: {isolation_info['type']}")

    async def stop(self):
        """Stop the deployment."""
        if self._sandbox is not None:
            await self._sandbox.stop()
            self._sandbox = None
            logger.info("Lightweight deployment stopped")

    @property
    def runtime(self) -> LightweightSandbox:
        """Get the runtime (LightweightSandbox).

        Returns:
            LightweightSandbox instance.

        Raises:
            DeploymentNotStartedError: If deployment not started.
        """
        if self._sandbox is None:
            raise DeploymentNotStartedError()
        return self._sandbox

    @property
    def config(self) -> LightweightDeploymentConfig:
        """Get the deployment config."""
        return self._config

    def get_isolation_info(self) -> dict:
        """Get isolation information.

        Returns:
            Dictionary with isolation details.
        """
        if self._sandbox:
            return self._sandbox.get_isolation_info()
        return {"type": "unknown", "available": False, "description": "Sandbox not started"}
