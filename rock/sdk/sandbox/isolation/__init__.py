"""
Isolation providers for lightweight sandbox runtime.

Supports multiple isolation mechanisms:
- NoIsolation: Direct execution without isolation (fastest, for testing)
- SandboxExecIsolation: macOS sandbox-exec (syscall filtering)
- BubblewrapIsolation: Linux bubblewrap/bwrap (namespace isolation)
"""

from rock.sdk.sandbox.isolation.base import AbstractIsolationProvider, IsolationConfig
from rock.sdk.sandbox.isolation.factory import IsolationProviderFactory
from rock.sdk.sandbox.isolation.none import NoIsolation

__all__ = [
    "AbstractIsolationProvider",
    "IsolationConfig",
    "IsolationProviderFactory",
    "NoIsolation",
]
