"""Tests for LightweightSandbox."""

import pytest

from rock.admin.proto.request import SandboxCommand as Command
from rock.admin.proto.request import SandboxCreateBashSessionRequest as CreateBashSessionRequest
from rock.admin.proto.request import SandboxReadFileRequest as ReadFileRequest
from rock.admin.proto.request import SandboxWriteFileRequest as WriteFileRequest
from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig


class TestLightweightSandboxConfig:
    """Tests for LightweightSandboxConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = LightweightSandboxConfig()

        assert config.isolation_mode == "auto"
        assert config.working_dir is None
        assert config.env_vars == {}
        assert config.allow_network is True
        assert config.allow_read_paths == ["/"]
        assert config.allow_write_paths == []

    def test_custom_config(self):
        """Test custom configuration."""
        config = LightweightSandboxConfig(
            isolation_mode="none",
            env_vars={"TEST": "value"},
            allow_network=False,
        )

        assert config.isolation_mode == "none"
        assert config.env_vars["TEST"] == "value"
        assert config.allow_network is False

    def test_to_isolation_config(self):
        """Test conversion to IsolationConfig."""
        config = LightweightSandboxConfig(
            allow_network=False,
            allow_write_paths=["/tmp"],
        )
        isolation_config = config.to_isolation_config()

        assert isolation_config.allow_network is False
        assert "/tmp" in isolation_config.allow_write_paths


class TestLightweightSandbox:
    """Tests for LightweightSandbox."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping sandbox."""
        sandbox = LightweightSandbox()

        # Initially not alive
        status = await sandbox.is_alive()
        assert status.is_alive is False

        # Start
        await sandbox.start()
        status = await sandbox.is_alive()
        assert status.is_alive is True

        # Stop
        await sandbox.stop()
        status = await sandbox.is_alive()
        assert status.is_alive is False

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        async with LightweightSandbox() as sandbox:
            status = await sandbox.is_alive()
            assert status.is_alive is True

        # After exit, should be stopped
        status = await sandbox.is_alive()
        assert status.is_alive is False

    @pytest.mark.asyncio
    async def test_create_session_and_run(self):
        """Test creating session and running commands."""
        async with LightweightSandbox() as sandbox:
            # Create session
            response = await sandbox.create_session(
                CreateBashSessionRequest(session="test")
            )
            assert response is not None

            # Run command
            result = await sandbox.arun("echo hello", session="test")
            assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_arun_auto_session(self):
        """Test arun with automatic session creation."""
        async with LightweightSandbox() as sandbox:
            result = await sandbox.arun("echo world", session="auto_session")
            assert "world" in result.output

    @pytest.mark.asyncio
    async def test_read_write_file(self):
        """Test file read/write operations."""
        import tempfile
        from pathlib import Path

        async with LightweightSandbox() as sandbox:
            # Create temp file path
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
                temp_path = f.name

            try:
                # Write file
                await sandbox.write_file(
                    WriteFileRequest(path=temp_path, content="test content")
                )

                # Read file
                result = await sandbox.read_file(
                    ReadFileRequest(path=temp_path)
                )
                assert result.content == "test content"
            finally:
                Path(temp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_execute_command(self):
        """Test execute (subprocess) command."""
        async with LightweightSandbox() as sandbox:
            result = await sandbox.execute(
                Command(command=["echo", "subprocess test"])
            )
            assert result.exit_code == 0
            assert "subprocess test" in result.stdout

    @pytest.mark.asyncio
    async def test_isolation_info(self):
        """Test getting isolation info."""
        config = LightweightSandboxConfig(isolation_mode="none")
        sandbox = LightweightSandbox(config)

        # Before start
        info = sandbox.get_isolation_info()
        assert "type" in info

        # After start
        await sandbox.start()
        info = sandbox.get_isolation_info()
        assert info["type"] == "none"

        await sandbox.stop()

    @pytest.mark.asyncio
    async def test_not_started_error(self):
        """Test operations before start raise errors."""
        sandbox = LightweightSandbox()

        with pytest.raises(RuntimeError, match="not started"):
            await sandbox.create_session(
                CreateBashSessionRequest(session="test")
            )

    def test_str_repr(self):
        """Test string representations."""
        sandbox = LightweightSandbox()

        str_repr = str(sandbox)
        assert "LightweightSandbox" in str_repr
        assert "stopped" in str_repr

        repr_str = repr(sandbox)
        assert "LightweightSandbox" in repr_str
        assert "config=" in repr_str


class TestLightweightSandboxWithIsolation:
    """Tests for LightweightSandbox with different isolation modes."""

    @pytest.mark.asyncio
    async def test_no_isolation(self):
        """Test with no isolation."""
        config = LightweightSandboxConfig(isolation_mode="none")
        async with LightweightSandbox(config) as sandbox:
            info = sandbox.get_isolation_info()
            assert info["type"] == "none"

            result = await sandbox.arun("echo isolated", session="test")
            assert "isolated" in result.output

    @pytest.mark.asyncio
    async def test_auto_isolation(self):
        """Test with auto isolation selection."""
        config = LightweightSandboxConfig(isolation_mode="auto")
        async with LightweightSandbox(config) as sandbox:
            info = sandbox.get_isolation_info()
            # Should have selected some isolation mode
            assert info["type"] in ["none", "sandbox-exec", "bubblewrap"]

            result = await sandbox.arun("pwd", session="test")
            assert result.output.strip()  # Should have some output
