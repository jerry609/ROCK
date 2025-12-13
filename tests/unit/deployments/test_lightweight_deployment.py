"""Tests for LightweightDeployment."""

import pytest

from rock.admin.proto.request import SandboxCreateBashSessionRequest as CreateBashSessionRequest
from rock.deployments.config import LightweightDeploymentConfig
from rock.deployments.lightweight import LightweightDeployment


class TestLightweightDeploymentConfig:
    """Tests for LightweightDeploymentConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = LightweightDeploymentConfig()

        assert config.isolation_mode == "auto"
        assert config.type == "lightweight"

    def test_get_deployment(self):
        """Test creating deployment from config."""
        config = LightweightDeploymentConfig()
        deployment = config.get_deployment()

        assert isinstance(deployment, LightweightDeployment)


class TestLightweightDeployment:
    """Tests for LightweightDeployment."""

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test starting and stopping deployment."""
        deployment = LightweightDeployment()

        # Initially not alive
        status = await deployment.is_alive()
        assert status.is_alive is False

        # Start
        await deployment.start()
        status = await deployment.is_alive()
        assert status.is_alive is True

        # Stop
        await deployment.stop()
        status = await deployment.is_alive()
        assert status.is_alive is False

    @pytest.mark.asyncio
    async def test_runtime_access(self):
        """Test accessing runtime."""
        from rock.rocklet.exceptions import DeploymentNotStartedError

        deployment = LightweightDeployment()

        # Before start
        with pytest.raises(DeploymentNotStartedError):
            _ = deployment.runtime

        # After start
        await deployment.start()
        runtime = deployment.runtime
        assert runtime is not None

        await deployment.stop()

    @pytest.mark.asyncio
    async def test_from_config(self):
        """Test creating from config."""
        from rock.deployments.lightweight import LightweightDeploymentConfig

        config = LightweightDeploymentConfig(
            isolation_mode="none",
            allow_network=False,
        )
        deployment = LightweightDeployment.from_config(config)

        await deployment.start()
        info = deployment.get_isolation_info()
        assert info["type"] == "none"

        await deployment.stop()

    @pytest.mark.asyncio
    async def test_run_command(self):
        """Test running commands through deployment."""
        deployment = LightweightDeployment()
        await deployment.start()

        runtime = deployment.runtime
        await runtime.create_session(CreateBashSessionRequest(session="test"))
        result = await runtime.arun("echo deployment test", session="test")

        assert "deployment test" in result.output

        await deployment.stop()
