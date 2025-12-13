"""
Lightweight Sandbox - Local sandbox without Docker/Ray/Admin dependencies.

This module provides a lightweight sandbox implementation that runs directly
on the local machine, optionally with process isolation using platform-native
mechanisms (sandbox-exec on macOS, bubblewrap on Linux).

Usage:
    from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig

    # Create with default config (auto isolation)
    sandbox = LightweightSandbox()
    await sandbox.start()

    # Create session and run commands
    await sandbox.create_session(CreateBashSessionRequest(session="main"))
    result = await sandbox.arun("echo Hello", session="main")
    print(result.output)

    await sandbox.stop()
"""

import asyncio
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from rock.actions.sandbox.base import AbstractSandbox
from rock.actions.sandbox.request import UploadRequest
from rock.actions.sandbox.response import (
    CloseResponse,
    CloseSessionResponse,
    CommandResponse,
    CreateSessionResponse,
    IsAliveResponse,
    Observation,
    ReadFileResponse,
    UploadResponse,
    WriteFileResponse,
)
from rock.admin.proto.request import SandboxAction as Action
from rock.admin.proto.request import SandboxBashAction as BashAction
from rock.admin.proto.request import SandboxCloseSessionRequest as CloseSessionRequest
from rock.admin.proto.request import SandboxCommand as Command
from rock.admin.proto.request import SandboxCreateBashSessionRequest as CreateBashSessionRequest
from rock.admin.proto.request import SandboxCreateSessionRequest as CreateSessionRequest
from rock.admin.proto.request import SandboxReadFileRequest as ReadFileRequest
from rock.admin.proto.request import SandboxWriteFileRequest as WriteFileRequest
from rock.rocklet.local_sandbox import LocalSandboxRuntime
from rock.sdk.sandbox.isolation.base import IsolationConfig
from rock.sdk.sandbox.isolation.factory import IsolationMode, IsolationProviderFactory

logger = logging.getLogger(__name__)

# Global lock to serialize all pexpect operations across all LightweightSandbox instances.
# This is necessary because LocalSandboxRuntime uses a shared global ThreadPoolExecutor,
# and concurrent pexpect operations can cause race conditions where shell.before is empty.
# TODO: Fix the root cause in LocalSandboxRuntime by using per-instance executor
_global_session_lock: asyncio.Lock | None = None


def _get_global_session_lock() -> asyncio.Lock:
    """Get or create the global session lock."""
    global _global_session_lock
    if _global_session_lock is None:
        _global_session_lock = asyncio.Lock()
    return _global_session_lock


class LightweightSandboxConfig(BaseModel):
    """Configuration for LightweightSandbox.

    Attributes:
        isolation_mode: Isolation mechanism to use.
            - "none": No isolation, direct execution (fastest)
            - "sandbox-exec": macOS sandbox-exec (moderate isolation)
            - "bubblewrap": Linux bubblewrap/bwrap (strong isolation)
            - "auto": Auto-detect best available isolation
        working_dir: Working directory for the sandbox.
        env_vars: Additional environment variables.
        allow_network: Whether to allow network access (for isolated modes).
        allow_read_paths: Paths allowed for reading (for isolated modes).
        allow_write_paths: Paths allowed for writing (for isolated modes).
    """

    isolation_mode: IsolationMode = Field(
        default="auto",
        description="Isolation mode: none, sandbox-exec, bubblewrap, or auto",
    )
    working_dir: Path | None = Field(
        default=None,
        description="Working directory for the sandbox",
    )
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Additional environment variables",
    )
    allow_network: bool = Field(
        default=True,
        description="Allow network access (for isolated modes)",
    )
    allow_read_paths: list[str] = Field(
        default=["/"],
        description="Paths allowed for reading (for isolated modes)",
    )
    allow_write_paths: list[str] = Field(
        default_factory=list,
        description="Paths allowed for writing (for isolated modes)",
    )

    def to_isolation_config(self) -> IsolationConfig:
        """Convert to IsolationConfig for the isolation provider."""
        return IsolationConfig(
            allow_network=self.allow_network,
            allow_read_paths=self.allow_read_paths,
            allow_write_paths=self.allow_write_paths,
            working_dir=self.working_dir,
            env_vars=self.env_vars,
        )


class LightweightSandbox(AbstractSandbox):
    """Lightweight local sandbox without Docker/Ray/Admin dependencies.

    This sandbox runs commands directly on the local machine using
    LocalSandboxRuntime, optionally with process isolation using
    platform-native mechanisms.

    Compatible with the existing Sandbox API, allowing seamless switching
    between remote (Docker-based) and local (lightweight) sandboxes.

    Note:
        This class uses an asyncio.Lock to serialize session creation and
        command execution. This is necessary to work around a race condition
        in LocalSandboxRuntime where multiple concurrent pexpect operations
        on a shared ThreadPoolExecutor can cause empty output.
        TODO: Fix the root cause in LocalSandboxRuntime by using per-instance executor

    Attributes:
        config: Sandbox configuration.
        agent: Optional agent attached to this sandbox.
        remote_user: Remote user manager (for compatibility with Sandbox).
    """

    def __init__(self, config: LightweightSandboxConfig | None = None):
        """Initialize LightweightSandbox.

        Args:
            config: Configuration for the sandbox. If None, uses defaults.
        """
        self._config = config or LightweightSandboxConfig()
        self._runtime: LocalSandboxRuntime | None = None
        self._isolation = None
        self._started = False

        # For compatibility with Sandbox class
        self.agent = None
        self.remote_user = None

    @property
    def config(self) -> LightweightSandboxConfig:
        """Get the sandbox configuration."""
        return self._config

    @property
    def runtime(self) -> LocalSandboxRuntime:
        """Get the underlying runtime.

        Raises:
            RuntimeError: If sandbox is not started.
        """
        if self._runtime is None:
            raise RuntimeError("Sandbox not started. Call start() first.")
        return self._runtime

    @property
    def isolation(self):
        """Get the isolation provider."""
        return self._isolation

    async def start(self):
        """Start the sandbox.

        Initializes the isolation provider and runtime.
        """
        if self._started:
            logger.warning("Sandbox already started")
            return

        # Create isolation provider
        isolation_config = self._config.to_isolation_config()
        self._isolation = IsolationProviderFactory.create(
            mode=self._config.isolation_mode,
            config=isolation_config,
        )

        # Log isolation info
        isolation_info = self._isolation.get_isolation_info()
        logger.info(f"Starting lightweight sandbox with isolation: {isolation_info['type']}")

        # Create runtime
        self._runtime = LocalSandboxRuntime()

        # Initialize remote_user for compatibility
        try:
            from rock.sdk.sandbox.remote_user import LinuxRemoteUser
            self.remote_user = LinuxRemoteUser(self)
        except ImportError:
            pass

        self._started = True
        logger.info("Lightweight sandbox started successfully")

    async def stop(self):
        """Stop the sandbox and clean up resources."""
        if not self._started:
            return

        if self._runtime:
            await self._runtime.close()
            self._runtime = None

        self._isolation = None
        self._started = False
        logger.info("Lightweight sandbox stopped")

    async def is_alive(self, *, timeout: float | None = None) -> IsAliveResponse:
        """Check if the sandbox is alive.

        Args:
            timeout: Timeout in seconds (unused for local sandbox).

        Returns:
            IsAliveResponse indicating the sandbox status.
        """
        if not self._started or self._runtime is None:
            return IsAliveResponse(is_alive=False, message="Sandbox not started")
        return await self._runtime.is_alive(timeout=timeout)

    async def create_session(self, request: CreateSessionRequest) -> CreateSessionResponse:
        """Create a new session in the sandbox.

        Args:
            request: Session creation request.

        Returns:
            CreateSessionResponse with session details.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")

        async with _get_global_session_lock():
            # For bash sessions, enable environment inheritance for proper shell behavior
            if isinstance(request, CreateBashSessionRequest):
                request.env_enable = True
                if request.env is None:
                    request.env = {}
                # Apply isolation environment if needed
                if self._isolation:
                    request.env = self._isolation.wrap_session_env(request.env)

            response = await self._runtime.create_session(request)
            # Allow shell to fully settle after initialization
            # This delay is critical to avoid race conditions with pexpect
            await asyncio.sleep(0.5)
            return response

    async def run_in_session(self, action: Action) -> Observation:
        """Run an action in an existing session.

        Args:
            action: Action to execute.

        Returns:
            Observation with execution results.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")
        async with _get_global_session_lock():
            return await self._runtime.run_in_session(action)

    async def close_session(self, request: CloseSessionRequest) -> CloseSessionResponse:
        """Close an existing session.

        Args:
            request: Session close request.

        Returns:
            CloseSessionResponse confirming closure.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")
        return await self._runtime.close_session(request)

    async def execute(self, command: Command) -> CommandResponse:
        """Execute a command outside of any session.

        Args:
            command: Command to execute.

        Returns:
            CommandResponse with execution results.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")

        # Optionally wrap command with isolation
        # Note: For subprocess execution, isolation wrapping may be limited
        return await self._runtime.execute(command)

    async def read_file(self, request: ReadFileRequest) -> ReadFileResponse:
        """Read a file from the sandbox.

        Args:
            request: File read request.

        Returns:
            ReadFileResponse with file contents.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")
        return await self._runtime.read_file(request)

    async def write_file(self, request: WriteFileRequest) -> WriteFileResponse:
        """Write content to a file in the sandbox.

        Args:
            request: File write request.

        Returns:
            WriteFileResponse confirming write.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")
        return await self._runtime.write_file(request)

    async def upload(self, request: UploadRequest) -> UploadResponse:
        """Upload a file to the sandbox.

        Args:
            request: Upload request.

        Returns:
            UploadResponse confirming upload.
        """
        if not self._started:
            raise RuntimeError("Sandbox not started. Call start() first.")
        return await self._runtime.upload(request)

    async def close(self) -> CloseResponse:
        """Close the sandbox (alias for stop)."""
        await self.stop()
        return CloseResponse()

    # Convenience methods for compatibility with Sandbox class

    async def arun(
        self,
        cmd: str,
        session: str = "default",
        timeout: float = 120,
        check: Literal["raise", "ignore", "silent"] = "silent",
    ) -> Observation:
        """Run a command in a session (convenience method).

        This provides a simpler interface similar to Sandbox.arun().

        Args:
            cmd: Command to execute.
            session: Session name (creates if doesn't exist).
            timeout: Command timeout in seconds.
            check: How to handle non-zero exit codes.

        Returns:
            Observation with execution results.
        """
        max_retries = 3
        retry_delay = 0.2

        async with _get_global_session_lock():
            # Ensure session exists
            if session not in self._runtime.sessions:
                # Create session inline (without re-acquiring lock)
                request = CreateBashSessionRequest(session=session)
                request.env_enable = True
                if request.env is None:
                    request.env = {}
                if self._isolation:
                    request.env = self._isolation.wrap_session_env(request.env)
                await self._runtime.create_session(request)
                # Allow shell to fully settle after initialization
                await asyncio.sleep(0.5)

            action = BashAction(
                command=cmd,
                session=session,
                timeout=timeout,
                check=check,
            )

            # Retry logic to handle race condition in pexpect
            # where shell.before may be empty due to timing issues
            for attempt in range(max_retries):
                result = await self._runtime.run_in_session(action)
                if result.output.strip():
                    return result
                # If output is empty for a command that should produce output,
                # wait and retry by re-running the command
                if attempt < max_retries - 1:
                    logger.debug(
                        f"Empty output for command '{cmd}', retrying "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)

            return result

    def get_isolation_info(self) -> dict:
        """Get information about the current isolation configuration.

        Returns:
            Dictionary with isolation details.
        """
        if self._isolation:
            return self._isolation.get_isolation_info()
        return {"type": "none", "available": True, "description": "Sandbox not started"}

    def __str__(self) -> str:
        """Return user-friendly string representation."""
        status = "running" if self._started else "stopped"
        isolation = self._config.isolation_mode
        return f"LightweightSandbox(status={status}, isolation={isolation})"

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return (
            f"LightweightSandbox("
            f"config={self._config!r}, "
            f"started={self._started}, "
            f"runtime={self._runtime!r}, "
            f"isolation={self._isolation!r})"
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
        return False
