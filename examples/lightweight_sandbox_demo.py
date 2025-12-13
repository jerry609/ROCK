"""
Lightweight Sandbox Demo - Run commands locally without Docker/Admin dependencies.

This demo shows how to use LightweightSandbox for local command execution
with optional process isolation using platform-native mechanisms:
- macOS: sandbox-exec
- Linux: bubblewrap (bwrap)
"""

import asyncio

from rock.admin.proto.request import SandboxCreateBashSessionRequest as CreateBashSessionRequest
from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig


async def basic_usage():
    """Basic usage with default configuration (auto isolation)."""
    print("=" * 60)
    print("Basic Usage - Auto Isolation")
    print("=" * 60)

    # Create sandbox with default config (auto-selects best isolation)
    async with LightweightSandbox() as sandbox:
        # Get isolation info
        info = sandbox.get_isolation_info()
        print(f"Isolation type: {info['type']}")

        # Run commands
        result = await sandbox.arun("echo Hello from LightweightSandbox!", session="main")
        print(f"Output: {result.output}")

        result = await sandbox.arun("pwd", session="main")
        print(f"Working directory: {result.output}")


async def no_isolation_usage():
    """Usage with no isolation (fastest, direct execution)."""
    print("\n" + "=" * 60)
    print("No Isolation Mode - Direct Execution")
    print("=" * 60)

    config = LightweightSandboxConfig(isolation_mode="none")

    async with LightweightSandbox(config) as sandbox:
        info = sandbox.get_isolation_info()
        print(f"Isolation type: {info['type']}")

        result = await sandbox.arun("python3 --version", session="dev")
        print(f"Python version: {result.output}")


async def custom_environment():
    """Usage with custom environment variables."""
    print("\n" + "=" * 60)
    print("Custom Environment Variables")
    print("=" * 60)

    config = LightweightSandboxConfig(
        isolation_mode="none",
        env_vars={"MY_VAR": "Hello from env!", "DEBUG": "true"},
    )

    async with LightweightSandbox(config) as sandbox:
        result = await sandbox.arun("echo $MY_VAR", session="env_test")
        print(f"Custom env var: {result.output}")


async def file_operations():
    """Demonstrate file read/write operations."""
    print("\n" + "=" * 60)
    print("File Operations")
    print("=" * 60)

    import tempfile
    from pathlib import Path

    from rock.admin.proto.request import SandboxReadFileRequest as ReadFileRequest
    from rock.admin.proto.request import SandboxWriteFileRequest as WriteFileRequest

    async with LightweightSandbox() as sandbox:
        # Create a temp file path
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            temp_path = f.name

        try:
            # Write content
            await sandbox.write_file(
                WriteFileRequest(path=temp_path, content="Hello from LightweightSandbox!")
            )
            print(f"Wrote to: {temp_path}")

            # Read content back
            result = await sandbox.read_file(ReadFileRequest(path=temp_path))
            print(f"Read content: {result.content}")
        finally:
            Path(temp_path).unlink(missing_ok=True)


async def subprocess_execution():
    """Execute commands via subprocess (not shell session)."""
    print("\n" + "=" * 60)
    print("Subprocess Execution")
    print("=" * 60)

    from rock.admin.proto.request import SandboxCommand as Command

    async with LightweightSandbox() as sandbox:
        # Execute as subprocess (not through bash session)
        result = await sandbox.execute(Command(command=["echo", "subprocess", "test"]))
        print(f"Subprocess output: {result.stdout}")
        print(f"Exit code: {result.exit_code}")


async def main():
    """Run all demos."""
    print("\nLightweight Sandbox Demo")
    print("No Docker or Admin server required!\n")

    await basic_usage()
    await no_isolation_usage()
    await custom_environment()
    await file_operations()
    await subprocess_execution()

    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
