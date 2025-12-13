"""
Sandbox CLI command for lightweight sandbox operations.

Provides commands to start, stop, and interact with lightweight sandboxes
without requiring Docker, Ray, or Admin server.

Usage:
    rock sandbox start [--mode lightweight] [--isolation auto|none|sandbox-exec|bubblewrap] [-i]
    rock sandbox shell
    rock sandbox stop
    rock sandbox info
"""

import argparse
import asyncio
import sys

from rock.cli.command.command import Command as CliCommand
from rock.logger import init_logger

logger = init_logger("rock.cli.sandbox")


class SandboxCommand(CliCommand):
    """CLI command for sandbox operations."""

    name = "sandbox"

    def __init__(self):
        super().__init__()
        self._sandbox = None

    async def arun(self, args: argparse.Namespace):
        """Execute sandbox command."""
        if not args.sandbox_command:
            raise ValueError("Sandbox action is required (start, stop, shell, info)")

        if args.sandbox_command == "start":
            await self._start(args)
        elif args.sandbox_command == "stop":
            await self._stop(args)
        elif args.sandbox_command == "shell":
            await self._shell(args)
        elif args.sandbox_command == "info":
            await self._info(args)
        else:
            raise ValueError(f"Unknown sandbox action '{args.sandbox_command}'")

    async def _start(self, args: argparse.Namespace):
        """Start a sandbox."""
        mode = getattr(args, "mode", "lightweight")

        if mode == "lightweight":
            await self._start_lightweight(args)
        elif mode == "docker":
            logger.info("Docker mode requires admin server. Use 'rock admin start' first.")
            print("Docker mode requires admin server. Use 'rock admin start' first.")
            print("Then use the SDK: Sandbox(SandboxConfig(image='...')).start()")
        else:
            raise ValueError(f"Unknown mode: {mode}")

    async def _start_lightweight(self, args: argparse.Namespace):
        """Start a lightweight sandbox."""
        from rock.sdk.sandbox.isolation.factory import IsolationProviderFactory
        from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig

        isolation_mode = getattr(args, "isolation", "auto")
        workdir = getattr(args, "workdir", None)
        interactive = getattr(args, "interactive", False)

        # Show available isolation modes
        available = IsolationProviderFactory.list_available()
        recommended = IsolationProviderFactory.get_recommended()

        print("Lightweight Sandbox")
        print("=" * 40)
        print(f"Isolation modes available:")
        for mode, is_available in available.items():
            status = "available" if is_available else "not available"
            rec = " (recommended)" if mode == recommended else ""
            print(f"  - {mode}: {status}{rec}")
        print()

        # Create config
        config = LightweightSandboxConfig(
            isolation_mode=isolation_mode,
            working_dir=workdir,
        )

        # Create and start sandbox
        sandbox = LightweightSandbox(config)
        await sandbox.start()

        isolation_info = sandbox.get_isolation_info()
        print(f"Started with isolation: {isolation_info['type']}")
        print()

        if interactive:
            await self._interactive_shell(sandbox)
        else:
            print("Sandbox started. Use 'rock sandbox shell' to interact.")
            print("Or use the SDK:")
            print()
            print("  from rock.sdk.sandbox.lightweight import LightweightSandbox")
            print("  sandbox = LightweightSandbox()")
            print("  await sandbox.start()")
            print("  result = await sandbox.arun('echo hello', session='main')")
            print()

            # Keep running until interrupted
            print("Press Ctrl+C to stop the sandbox...")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping sandbox...")
                await sandbox.stop()
                print("Sandbox stopped.")

    async def _stop(self, args: argparse.Namespace):
        """Stop running sandboxes."""
        print("Note: Lightweight sandboxes are process-based and stop automatically.")
        print("If you started a sandbox with 'rock sandbox start', use Ctrl+C to stop it.")

    async def _shell(self, args: argparse.Namespace):
        """Start an interactive shell in a new lightweight sandbox."""
        from rock.sdk.sandbox.lightweight import LightweightSandbox, LightweightSandboxConfig

        isolation_mode = getattr(args, "isolation", "auto")

        config = LightweightSandboxConfig(isolation_mode=isolation_mode)
        sandbox = LightweightSandbox(config)
        await sandbox.start()

        print(f"Starting interactive shell (isolation: {sandbox.get_isolation_info()['type']})")
        print("Type 'exit' to quit.")
        print()

        await self._interactive_shell(sandbox)
        await sandbox.stop()

    async def _interactive_shell(self, sandbox):
        """Run interactive shell session."""
        from rock.actions.sandbox.request import CreateBashSessionRequest

        # Create session
        session_name = "interactive"
        await sandbox.create_session(CreateBashSessionRequest(session=session_name))

        # Get current directory for prompt
        result = await sandbox.arun("pwd", session=session_name)
        cwd = result.output.strip() if result.output else "~"

        while True:
            try:
                # Simple prompt
                prompt = f"sandbox:{cwd}$ "
                cmd = input(prompt)

                if not cmd.strip():
                    continue

                if cmd.strip() in ("exit", "quit"):
                    print("Exiting shell...")
                    break

                # Execute command
                result = await sandbox.arun(cmd, session=session_name)

                # Print output
                if result.output:
                    print(result.output)

                # Update cwd
                if cmd.strip().startswith("cd "):
                    pwd_result = await sandbox.arun("pwd", session=session_name)
                    cwd = pwd_result.output.strip() if pwd_result.output else cwd

            except KeyboardInterrupt:
                print("\n(Use 'exit' to quit)")
            except EOFError:
                print("\nExiting shell...")
                break
            except Exception as e:
                print(f"Error: {e}")

    async def _info(self, args: argparse.Namespace):
        """Show sandbox information."""
        import platform

        from rock.sdk.sandbox.isolation.factory import IsolationProviderFactory

        print("Sandbox Environment Info")
        print("=" * 40)
        print(f"Platform: {platform.system()} {platform.release()}")
        print(f"Machine: {platform.machine()}")
        print()

        print("Isolation Providers:")
        available = IsolationProviderFactory.list_available()
        recommended = IsolationProviderFactory.get_recommended()

        for mode, is_available in available.items():
            status = "available" if is_available else "not available"
            rec = " (recommended)" if mode == recommended else ""
            print(f"  - {mode}: {status}{rec}")

        print()
        print("Installation hints for unavailable providers:")
        if not available.get("bubblewrap", False) and platform.system() == "Linux":
            print("  bubblewrap: apt install bubblewrap  # Debian/Ubuntu")
            print("              yum install bubblewrap  # RHEL/CentOS")
        if not available.get("sandbox-exec", False) and platform.system() == "Darwin":
            print("  sandbox-exec: Built into macOS, should be available")

    @staticmethod
    async def add_parser_to(subparsers: argparse._SubParsersAction):
        """Add sandbox subparser."""
        sandbox_parser = subparsers.add_parser(
            "sandbox",
            help="Lightweight sandbox operations",
            description="Start and manage lightweight sandboxes without Docker/Ray dependencies.",
        )
        sandbox_subparsers = sandbox_parser.add_subparsers(
            dest="sandbox_command",
            help="Sandbox commands",
        )

        # rock sandbox start
        start_parser = sandbox_subparsers.add_parser(
            "start",
            help="Start a sandbox",
            description="Start a new lightweight sandbox.",
        )
        start_parser.add_argument(
            "--mode",
            choices=["lightweight", "docker"],
            default="lightweight",
            help="Sandbox mode (default: lightweight)",
        )
        start_parser.add_argument(
            "--isolation",
            choices=["none", "sandbox-exec", "bubblewrap", "auto"],
            default="auto",
            help="Isolation mode (default: auto)",
        )
        start_parser.add_argument(
            "-i", "--interactive",
            action="store_true",
            help="Start interactive shell after sandbox starts",
        )
        start_parser.add_argument(
            "--workdir",
            type=str,
            help="Working directory for the sandbox",
        )

        # rock sandbox shell
        shell_parser = sandbox_subparsers.add_parser(
            "shell",
            help="Start interactive shell",
            description="Start an interactive shell in a new lightweight sandbox.",
        )
        shell_parser.add_argument(
            "--isolation",
            choices=["none", "sandbox-exec", "bubblewrap", "auto"],
            default="auto",
            help="Isolation mode (default: auto)",
        )

        # rock sandbox stop
        sandbox_subparsers.add_parser(
            "stop",
            help="Stop sandbox",
            description="Stop running sandboxes.",
        )

        # rock sandbox info
        sandbox_subparsers.add_parser(
            "info",
            help="Show sandbox info",
            description="Show sandbox environment information and available isolation modes.",
        )
