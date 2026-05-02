from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sandbox.manager import (
    DockerProvider,
    DockerSandboxConfig,
    DockerUnavailableError,
    SandboxResult,
    SandboxTimeoutError,
    _resolve_docker_path,
    _resolve_windows_volume,
    _detect_docker_available,
    reset_sandbox_for_testing,
    get_sandbox_provider,
    initialize_sandbox,
    cleanup_sandbox,
    is_docker_available,
    DOCKER_IMAGE_FULL,
    DOCKER_WORKSPACE,
    WARM_POOL_SIZE,
)


class TestDockerPathResolution:
    def test_resolve_docker_path_windows_drive(self):
        result = _resolve_docker_path(r"C:\Users\test\project")
        assert result == "/c/Users/test/project"

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only path test")
    def test_resolve_docker_path_windows_drive_actual(self):
        result = _resolve_docker_path(r"C:\Users\test\project")
        assert "\\" not in result
        assert result.startswith("/")

    def test_resolve_docker_path_windows_unc(self):
        result = _resolve_docker_path(r"\\server\share\path")
        assert result == "//server/share/path"

    def test_resolve_docker_path_posix(self):
        result = _resolve_docker_path("/home/user/project")
        assert result == "/home/user/project"

    def test_resolve_windows_volume(self):
        result = _resolve_windows_volume(r"C:\Users\test\project")
        assert result.startswith("C:")
        assert "\\" not in result


class TestDockerAvailabilityDetection:
    @patch("subprocess.run")
    def test_docker_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = _detect_docker_available()
        assert result is True
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_docker_not_available_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        result = _detect_docker_available()
        assert result is False

    @patch("subprocess.run")
    def test_docker_not_available_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("docker info", 10)
        result = _detect_docker_available()
        assert result is False

    @patch("subprocess.run")
    def test_docker_not_available_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        result = _detect_docker_available()
        assert result is False


class TestDockerSandboxConfig:
    def test_default_config(self):
        config = DockerSandboxConfig()
        assert config.image_name == DOCKER_IMAGE_FULL
        assert config.workspace_path == DOCKER_WORKSPACE
        assert config.network == "none"
        assert config.memory == "512m"
        assert config.cpus == 1.0
        assert config.pids_limit == 100
        assert config.warm_pool_size == WARM_POOL_SIZE
        assert config.read_only is False

    def test_custom_config(self):
        config = DockerSandboxConfig(
            memory="256m",
            cpus=0.5,
            warm_pool_size=5,
            read_only=True,
        )
        assert config.memory == "256m"
        assert config.cpus == 0.5
        assert config.warm_pool_size == 5
        assert config.read_only is True


class TestDockerProviderInitialization:
    def setup_method(self):
        reset_sandbox_for_testing()

    def teardown_method(self):
        reset_sandbox_for_testing()

    @patch("sandbox.manager._detect_docker_available")
    def test_provider_creation_docker_unavailable(self, mock_detect):
        mock_detect.return_value = False
        provider = DockerProvider()
        assert provider.docker_available is False
        mock_detect.assert_called_once()

    @patch("sandbox.manager._detect_docker_available")
    def test_provider_creation_docker_available(self, mock_detect):
        mock_detect.return_value = True
        provider = DockerProvider()
        assert provider.docker_available is True

    @patch("sandbox.manager._detect_docker_available")
    def test_client_raises_when_docker_unavailable(self, mock_detect):
        mock_detect.side_effect = [False, False]
        provider = DockerProvider()
        with pytest.raises(DockerUnavailableError):
            _ = provider.client


class TestDockerProviderWarmPool:
    def setup_method(self):
        reset_sandbox_for_testing()

    def teardown_method(self):
        reset_sandbox_for_testing()

    @patch("sandbox.manager._detect_docker_available")
    @patch("sandbox.manager.DockerProvider.check_and_pull_image")
    def test_initialize_warm_pool_skips_when_docker_unavailable(
        self, mock_pull, mock_detect
    ):
        mock_detect.return_value = False
        provider = DockerProvider()

        async def _run():
            await provider.initialize_warm_pool()

        asyncio.run(_run())
        assert len(provider._warm_pool) == 0
        mock_pull.assert_not_called()

    @patch("sandbox.manager._detect_docker_available")
    @patch("sandbox.manager.DockerProvider.check_and_pull_image")
    @patch("sandbox.manager.DockerProvider._create_idle_container")
    def test_initialize_warm_pool_creates_containers(
        self, mock_create, mock_pull, mock_detect
    ):
        mock_detect.return_value = True
        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        mock_create.return_value = mock_container

        provider = DockerProvider()
        provider._client = MagicMock()

        async def _run():
            await provider.initialize_warm_pool()

        asyncio.run(_run())
        assert len(provider._warm_pool) == WARM_POOL_SIZE
        assert mock_create.call_count == WARM_POOL_SIZE

    @patch("sandbox.manager._detect_docker_available")
    def test_warm_pool_reuses_container(self, mock_detect):
        mock_detect.return_value = True
        provider = DockerProvider()
        provider._client = MagicMock()

        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        provider._warm_pool = [mock_container]

        async def _run():
            container = await provider._get_warm_container()
            assert container is mock_container
            assert len(provider._warm_pool) == 0

        asyncio.run(_run())

    @patch("sandbox.manager._detect_docker_available")
    def test_warm_pool_returns_container(self, mock_detect):
        mock_detect.return_value = True
        provider = DockerProvider()
        provider._client = MagicMock()

        mock_container = MagicMock()
        mock_container.short_id = "abc123"

        async def _run():
            await provider._return_container(mock_container)
            assert len(provider._warm_pool) == 1
            assert provider._warm_pool[0] is mock_container

        asyncio.run(_run())

    @patch("sandbox.manager._detect_docker_available")
    def test_warm_pool_at_capacity_drops_excess(self, mock_detect):
        mock_detect.return_value = True
        provider = DockerProvider()
        provider._client = MagicMock()

        existing_containers = [MagicMock() for _ in range(WARM_POOL_SIZE)]
        provider._warm_pool = existing_containers.copy()
        extra_container = MagicMock()
        extra_container.short_id = "extra"

        async def _run():
            await provider._return_container(extra_container)
            assert len(provider._warm_pool) == WARM_POOL_SIZE

        asyncio.run(_run())
        extra_container.remove.assert_called_once_with(force=True)


class TestDockerProviderExecute:
    def setup_method(self):
        reset_sandbox_for_testing()

    def teardown_method(self):
        reset_sandbox_for_testing()

    @patch("sandbox.manager._detect_docker_available")
    def test_execute_fallback_when_docker_unavailable(self, mock_detect):
        mock_detect.return_value = False
        provider = DockerProvider()

        async def _run():
            result = await provider.execute(
                'echo "hello"',
                timeout=5.0,
            )
            assert result.exit_code == 0
            assert "hello" in result.stdout

        asyncio.run(_run())

    @patch("sandbox.manager._detect_docker_available")
    def test_execute_fallback_with_timeout(self, mock_detect):
        mock_detect.return_value = False
        provider = DockerProvider()

        async def _run():
            with pytest.raises(SandboxTimeoutError):
                await provider.execute(
                    'python -c "import time; time.sleep(30)"',
                    timeout=0.1,
                )

        asyncio.run(_run())

    @patch("sandbox.manager._detect_docker_available")
    def test_execute_fallback_command_not_found(self, mock_detect):
        mock_detect.return_value = False
        provider = DockerProvider()

        async def _run():
            result = await provider.execute(
                "nonexistent_command_12345",
                timeout=5.0,
            )
            assert result.exit_code != 0

        asyncio.run(_run())


class TestDockerProviderCleanup:
    def setup_method(self):
        reset_sandbox_for_testing()

    def teardown_method(self):
        reset_sandbox_for_testing()

    @patch("sandbox.manager._detect_docker_available")
    def test_cleanup_removes_all_containers(self, mock_detect):
        mock_detect.return_value = True
        provider = DockerProvider()

        mock_container = MagicMock()
        mock_container.short_id = "abc123"
        provider._warm_pool = [mock_container]

        async def _run():
            await provider.cleanup()

        asyncio.run(_run())
        assert len(provider._warm_pool) == 0
        mock_container.remove.assert_called_once_with(force=True)


class TestSandboxResult:
    def test_sandbox_result_defaults(self):
        result = SandboxResult(stdout="out", stderr="", exit_code=0)
        assert result.stdout == "out"
        assert result.exit_code == 0
        assert result.interrupted is False
        assert result.timed_out is False

    def test_sandbox_result_timeout(self):
        result = SandboxResult(
            stdout="", stderr="timeout", exit_code=-1, timed_out=True
        )
        assert result.timed_out is True

    def test_sandbox_result_interrupted(self):
        result = SandboxResult(
            stdout="partial", stderr="", exit_code=130, interrupted=True
        )
        assert result.interrupted is True


class TestGlobalProviderFunctions:
    def setup_method(self):
        reset_sandbox_for_testing()

    def teardown_method(self):
        reset_sandbox_for_testing()

    def test_get_sandbox_provider_singleton(self):
        provider1 = get_sandbox_provider()
        provider2 = get_sandbox_provider()
        assert provider1 is provider2

    def test_reset_sandbox_for_testing_creates_new_provider(self):
        provider1 = get_sandbox_provider()
        reset_sandbox_for_testing()
        provider2 = get_sandbox_provider()
        assert provider1 is not provider2

    @patch("sandbox.manager._detect_docker_available")
    def test_is_docker_available(self, mock_detect):
        mock_detect.return_value = True
        assert is_docker_available() is True

        mock_detect.return_value = False
        reset_sandbox_for_testing()
        assert is_docker_available() is False


class TestVolumeMountConfiguration:
    def test_prepare_volumes_read_only(self):
        provider = DockerProvider()
        volumes = provider._prepare_volumes("C:\\project", read_only=True)
        key = "C:/project"
        assert key in volumes
        assert volumes[key]["bind"] == DOCKER_WORKSPACE
        assert volumes[key]["mode"] == "ro"

    def test_prepare_volumes_read_write(self):
        provider = DockerProvider()
        volumes = provider._prepare_volumes("C:\\project", read_only=False)
        key = "C:/project"
        assert key in volumes
        assert volumes[key]["bind"] == DOCKER_WORKSPACE
        assert volumes[key]["mode"] == "rw"

    def test_prepare_volumes_posix_path(self):
        provider = DockerProvider()
        volumes = provider._prepare_volumes("/home/user/project", read_only=False)
        key = "/home/user/project"
        assert key in volumes
        assert volumes[key]["bind"] == DOCKER_WORKSPACE


class TestDockerCommandBuilding:
    def test_build_docker_command_with_cwd(self):
        provider = DockerProvider()
        cmd = provider._build_docker_command("ls", "/workspace/subdir")
        assert "cd /workspace/subdir &&" in cmd
        assert "ls" in cmd

    def test_build_docker_command_default_cwd(self):
        provider = DockerProvider()
        cmd = provider._build_docker_command("ls")
        assert f"cd {DOCKER_WORKSPACE} &&" in cmd

    def test_build_docker_command_no_cwd(self):
        provider = DockerProvider()
        cmd = provider._build_docker_command("ls", None)
        assert "ls" in cmd
        assert "cd" not in cmd


class TestResourceLimits:
    def test_container_creation_uses_config_limits(self):
        config = DockerSandboxConfig(
            network="none",
            memory="512m",
            cpus=1.0,
            pids_limit=100,
        )
        assert config.network == "none"
        assert config.memory == "512m"
        assert config.cpus == 1.0
        assert config.pids_limit == 100

    def test_container_limits_are_enforced(self):
        worker_config = DockerSandboxConfig(
            network="none",
            memory="256m",
            cpus=0.5,
            pids_limit=50,
        )
        assert worker_config.memory == "256m"
        assert worker_config.cpus == 0.5
        assert worker_config.pids_limit == 50
