"""Integration tests for LightweightSandbox.

These tests verify the LightweightSandbox works correctly in real-world scenarios
without Docker or Admin server dependencies.
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from rock.admin.proto.request import SandboxCommand as Command
from rock.admin.proto.request import SandboxCreateBashSessionRequest as CreateBashSessionRequest
from rock.admin.proto.request import SandboxReadFileRequest as ReadFileRequest
from rock.admin.proto.request import SandboxWriteFileRequest as WriteFileRequest
from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig


class TestLightweightSandboxIntegration:
    """Integration tests for LightweightSandbox."""

    @pytest.mark.asyncio
    async def test_basic_command_execution(self):
        """Test basic command execution without Docker."""
        async with LightweightSandbox() as sandbox:
            result = await sandbox.arun("echo 'Hello ROCK'", session="test")
            assert "Hello ROCK" in result.output

    @pytest.mark.asyncio
    async def test_session_persistence(self):
        """Test that session state persists across commands."""
        async with LightweightSandbox() as sandbox:
            # Set environment variable
            await sandbox.arun("export TEST_VAR='persistent_value'", session="persist")
            # Verify it persists
            result = await sandbox.arun("echo $TEST_VAR", session="persist")
            assert "persistent_value" in result.output

    @pytest.mark.asyncio
    async def test_working_directory_change(self):
        """Test working directory changes persist."""
        async with LightweightSandbox() as sandbox:
            # Create temp directory
            with tempfile.TemporaryDirectory() as tmpdir:
                await sandbox.arun(f"cd {tmpdir}", session="cd_test")
                result = await sandbox.arun("pwd", session="cd_test")
                assert tmpdir in result.output

    @pytest.mark.asyncio
    async def test_file_operations_workflow(self):
        """Test complete file operations workflow."""
        async with LightweightSandbox() as sandbox:
            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / "test.txt"
                test_content = "Hello from LightweightSandbox!"

                # Write file
                await sandbox.write_file(
                    WriteFileRequest(path=str(test_file), content=test_content)
                )

                # Read file via API
                read_result = await sandbox.read_file(
                    ReadFileRequest(path=str(test_file))
                )
                assert read_result.content == test_content

                # Read file via shell command
                shell_result = await sandbox.arun(f"cat {test_file}", session="file_test")
                assert test_content in shell_result.output

    @pytest.mark.asyncio
    async def test_subprocess_execution(self):
        """Test subprocess execution mode."""
        async with LightweightSandbox() as sandbox:
            result = await sandbox.execute(
                Command(command=["python3", "-c", "print('subprocess works')"])
            )
            assert result.exit_code == 0
            assert "subprocess works" in result.stdout

    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        """Test multiple independent sessions."""
        async with LightweightSandbox() as sandbox:
            # Set different values in different sessions
            await sandbox.arun("export SESSION_ID='session_1'", session="s1")
            await sandbox.arun("export SESSION_ID='session_2'", session="s2")

            # Verify isolation
            result1 = await sandbox.arun("echo $SESSION_ID", session="s1")
            result2 = await sandbox.arun("echo $SESSION_ID", session="s2")

            assert "session_1" in result1.output
            assert "session_2" in result2.output

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling for failed commands."""
        async with LightweightSandbox() as sandbox:
            # Command that fails (non-existent file)
            result = await sandbox.arun("cat /nonexistent/file/path", session="error_test")
            # Should not raise, but exit code indicates failure
            assert result.exit_code != 0 or "No such file" in result.output

    @pytest.mark.asyncio
    async def test_long_output_command(self):
        """Test command with long output."""
        async with LightweightSandbox() as sandbox:
            # Generate 100 lines of output
            result = await sandbox.arun(
                "for i in $(seq 1 100); do echo \"Line $i\"; done",
                session="long_output"
            )
            assert "Line 1" in result.output
            assert "Line 100" in result.output


class TestLightweightSandboxConcurrency:
    """Tests for concurrent usage patterns."""

    @pytest.mark.asyncio
    async def test_sequential_sandbox_instances(self):
        """Test sequential creation of multiple sandbox instances."""
        results = []
        for i in range(3):
            async with LightweightSandbox() as sandbox:
                result = await sandbox.arun(f"echo 'instance_{i}'", session="test")
                results.append(result.output)

        assert "instance_0" in results[0]
        assert "instance_1" in results[1]
        assert "instance_2" in results[2]

    @pytest.mark.asyncio
    async def test_concurrent_commands_same_sandbox(self):
        """Test concurrent commands within the same sandbox.

        Note: Due to global lock, these will be serialized but should all succeed.
        """
        async with LightweightSandbox() as sandbox:
            # Create multiple sessions
            await sandbox.create_session(CreateBashSessionRequest(session="concurrent_1"))
            await sandbox.create_session(CreateBashSessionRequest(session="concurrent_2"))
            await sandbox.create_session(CreateBashSessionRequest(session="concurrent_3"))

            # Run commands concurrently
            tasks = [
                sandbox.arun("echo 'cmd_1'", session="concurrent_1"),
                sandbox.arun("echo 'cmd_2'", session="concurrent_2"),
                sandbox.arun("echo 'cmd_3'", session="concurrent_3"),
            ]
            results = await asyncio.gather(*tasks)

            assert "cmd_1" in results[0].output
            assert "cmd_2" in results[1].output
            assert "cmd_3" in results[2].output

    @pytest.mark.asyncio
    async def test_stress_test_retry_mechanism(self):
        """Stress test to verify retry mechanism handles race conditions.

        This test creates multiple sandboxes and runs commands rapidly
        to trigger the race condition that the retry mechanism handles.
        """
        config = LightweightSandboxConfig(isolation_mode="none")
        passed = 0
        failed = 0

        for i in range(10):
            async with LightweightSandbox(config) as sandbox:
                result1 = await sandbox.arun(f"echo 'test_{i}_a'", session="stress_a")
                result2 = await sandbox.arun(f"echo 'test_{i}_b'", session="stress_b")

                if f"test_{i}_a" in result1.output and f"test_{i}_b" in result2.output:
                    passed += 1
                else:
                    failed += 1

        # All should pass due to retry mechanism
        assert passed == 10, f"Expected 10 passes, got {passed} (failed: {failed})"


class TestLightweightSandboxIsolation:
    """Tests for isolation modes."""

    @pytest.mark.asyncio
    async def test_no_isolation_mode(self):
        """Test with no isolation (direct execution)."""
        config = LightweightSandboxConfig(isolation_mode="none")
        async with LightweightSandbox(config) as sandbox:
            info = sandbox.get_isolation_info()
            assert info["type"] == "none"

            result = await sandbox.arun("whoami", session="no_iso")
            assert result.output.strip()  # Should return current user

    @pytest.mark.asyncio
    async def test_auto_isolation_mode(self):
        """Test with auto-detected isolation."""
        config = LightweightSandboxConfig(isolation_mode="auto")
        async with LightweightSandbox(config) as sandbox:
            info = sandbox.get_isolation_info()
            # Should select appropriate isolation for the platform
            assert info["type"] in ["none", "sandbox-exec", "bubblewrap"]

            result = await sandbox.arun("pwd", session="auto_iso")
            assert result.output.strip()

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not Path("/usr/bin/sandbox-exec").exists(),
        reason="sandbox-exec not available (not macOS)"
    )
    async def test_sandbox_exec_isolation(self):
        """Test macOS sandbox-exec isolation."""
        config = LightweightSandboxConfig(isolation_mode="sandbox-exec")
        async with LightweightSandbox(config) as sandbox:
            info = sandbox.get_isolation_info()
            assert info["type"] == "sandbox-exec"

            result = await sandbox.arun("echo 'sandboxed'", session="sandbox_exec")
            assert "sandboxed" in result.output
