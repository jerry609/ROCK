"""Tests for isolation providers."""

import platform

import pytest

from rock.sdk.sandbox.isolation import IsolationConfig, IsolationProviderFactory, NoIsolation
from rock.sdk.sandbox.isolation.factory import IsolationMode
from rock.sdk.sandbox.isolation.linux import BubblewrapIsolation
from rock.sdk.sandbox.isolation.macos import SandboxExecIsolation


class TestNoIsolation:
    """Tests for NoIsolation provider."""

    def test_is_available(self):
        """NoIsolation should always be available."""
        assert NoIsolation.is_available() is True

    def test_wrap_command_unchanged(self):
        """Commands should pass through unchanged."""
        isolation = NoIsolation()
        cmd = "echo hello world"
        assert isolation.wrap_command(cmd) == cmd

    def test_get_shell_command(self):
        """Should return standard bash."""
        isolation = NoIsolation()
        assert isolation.get_shell_command() == "/bin/bash"

    def test_get_isolation_info(self):
        """Should return correct info."""
        isolation = NoIsolation()
        info = isolation.get_isolation_info()
        assert info["type"] == "none"
        assert info["available"] is True


class TestSandboxExecIsolation:
    """Tests for macOS sandbox-exec isolation."""

    def test_is_available(self):
        """Should only be available on macOS."""
        is_available = SandboxExecIsolation.is_available()
        if platform.system() == "Darwin":
            # May or may not be available depending on sandbox-exec
            assert isinstance(is_available, bool)
        else:
            assert is_available is False

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_generate_profile(self):
        """Test profile generation."""
        config = IsolationConfig(
            allow_network=True,
            allow_read_paths=["/usr", "/home"],
            allow_write_paths=["/tmp"],
        )
        isolation = SandboxExecIsolation(config)
        profile = isolation.profile

        assert "(version 1)" in profile
        assert "(deny default)" in profile
        assert "(allow network*)" in profile
        assert '(subpath "/usr")' in profile

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_wrap_command(self):
        """Test command wrapping."""
        isolation = SandboxExecIsolation()
        wrapped = isolation.wrap_command("echo test")

        assert "sandbox-exec" in wrapped
        assert "echo test" in wrapped

    def test_get_isolation_info(self):
        """Test isolation info."""
        isolation = SandboxExecIsolation()
        info = isolation.get_isolation_info()

        assert info["type"] == "sandbox-exec"
        assert info["platform"] == "macOS"


class TestBubblewrapIsolation:
    """Tests for Linux bubblewrap isolation."""

    def test_is_available(self):
        """Should only be available on Linux with bwrap."""
        is_available = BubblewrapIsolation.is_available()
        if platform.system() == "Linux":
            # May or may not be available depending on bwrap installation
            assert isinstance(is_available, bool)
        else:
            assert is_available is False

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    def test_build_bwrap_args(self):
        """Test bwrap argument building."""
        config = IsolationConfig(
            allow_network=False,
            allow_write_paths=["/tmp/test"],
        )
        isolation = BubblewrapIsolation(config)
        args = isolation._build_bwrap_args()

        assert "bwrap" in args
        assert "--unshare-net" in args
        assert "--bind" in args

    @pytest.mark.skipif(platform.system() != "Linux", reason="Linux only")
    def test_wrap_command(self):
        """Test command wrapping."""
        isolation = BubblewrapIsolation()
        wrapped = isolation.wrap_command("echo test")

        assert "bwrap" in wrapped
        assert "echo test" in wrapped

    def test_get_isolation_info(self):
        """Test isolation info."""
        isolation = BubblewrapIsolation()
        info = isolation.get_isolation_info()

        assert info["type"] == "bubblewrap"
        assert info["platform"] == "Linux"


class TestIsolationProviderFactory:
    """Tests for isolation provider factory."""

    def test_create_none(self):
        """Test creating no isolation provider."""
        provider = IsolationProviderFactory.create("none")
        assert isinstance(provider, NoIsolation)

    def test_create_auto(self):
        """Test auto-detection."""
        provider = IsolationProviderFactory.create("auto")
        # Should return some valid provider
        assert provider is not None
        assert hasattr(provider, "wrap_command")

    def test_create_invalid_mode(self):
        """Test invalid mode raises error."""
        with pytest.raises(ValueError, match="Unknown isolation mode"):
            IsolationProviderFactory.create("invalid_mode")  # type: ignore

    def test_list_available(self):
        """Test listing available providers."""
        available = IsolationProviderFactory.list_available()

        assert "none" in available
        assert available["none"] is True  # NoIsolation always available
        assert "sandbox-exec" in available
        assert "bubblewrap" in available

    def test_get_recommended(self):
        """Test getting recommended provider."""
        recommended = IsolationProviderFactory.get_recommended()

        # Should return a valid mode
        assert recommended in ["none", "sandbox-exec", "bubblewrap"]

    @pytest.mark.skipif(
        not SandboxExecIsolation.is_available(),
        reason="sandbox-exec not available"
    )
    def test_create_sandbox_exec(self):
        """Test creating sandbox-exec provider."""
        provider = IsolationProviderFactory.create("sandbox-exec")
        assert isinstance(provider, SandboxExecIsolation)

    @pytest.mark.skipif(
        not BubblewrapIsolation.is_available(),
        reason="bubblewrap not available"
    )
    def test_create_bubblewrap(self):
        """Test creating bubblewrap provider."""
        provider = IsolationProviderFactory.create("bubblewrap")
        assert isinstance(provider, BubblewrapIsolation)


class TestIsolationConfig:
    """Tests for IsolationConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = IsolationConfig()

        assert config.allow_network is True
        assert config.allow_read_paths == ["/"]
        assert config.allow_write_paths == []
        assert config.working_dir is None
        assert config.env_vars == {}

    def test_custom_config(self):
        """Test custom configuration."""
        config = IsolationConfig(
            allow_network=False,
            allow_read_paths=["/usr", "/home"],
            allow_write_paths=["/tmp"],
            env_vars={"FOO": "bar"},
        )

        assert config.allow_network is False
        assert "/usr" in config.allow_read_paths
        assert "/tmp" in config.allow_write_paths
        assert config.env_vars["FOO"] == "bar"
