from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound, APIError
from docker.models.containers import Container

logger = logging.getLogger(__name__)

DOCKER_IMAGE_NAME = "py-cc-sandbox"
DOCKER_IMAGE_TAG = "1.0"
DOCKER_IMAGE_FULL = f"{DOCKER_IMAGE_NAME}:{DOCKER_IMAGE_TAG}"
DOCKER_WORKSPACE = "/workspace"
DOCKER_NETWORK = "none"
DOCKER_MEMORY = "512m"
DOCKER_CPUS = 1.0
DOCKER_PIDS_LIMIT = 100
WARM_POOL_SIZE = 3

SANDBOX_DOCKERFILE = Path(__file__).parent / "Dockerfile"


@dataclass
class DockerSandboxConfig:
    image_name: str = DOCKER_IMAGE_FULL
    workspace_path: str = DOCKER_WORKSPACE
    network: str = DOCKER_NETWORK
    memory: str = DOCKER_MEMORY
    cpus: float = DOCKER_CPUS
    pids_limit: int = DOCKER_PIDS_LIMIT
    warm_pool_size: int = WARM_POOL_SIZE
    read_only: bool = False


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    interrupted: bool = False
    timed_out: bool = False


class DockerUnavailableError(Exception):
    pass


class SandboxTimeoutError(Exception):
    pass


def _resolve_docker_path(host_path: str) -> str:
    if sys.platform == "win32":
        match = re.match(r"^([A-Za-z]):[/\\](.*)", host_path)
        if match:
            drive = match.group(1).lower()
            rest = match.group(2).replace("\\", "/")
            return f"/{drive}/{rest}"

        match = re.match(r"^//([^/]+)/(.*)", host_path)
        if match:
            return f"//{match.group(1)}/{match.group(2)}"

        return host_path.replace("\\", "/")

    return host_path


def _resolve_windows_volume(host_path: str) -> str:
    if sys.platform == "win32":
        match = re.match(r"^([A-Za-z]):[/\\]", host_path)
        if match:
            drive = match.group(1).upper()
            rest = host_path[2:].replace("\\", "/")
            return f"{drive}:{rest}"
        match = re.match(r"^\\\\[^\\]+\\[^\\]+", host_path)
        if match:
            return host_path.replace("\\", "/")
    return host_path


def _detect_docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


async def _detect_docker_available_async() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return False


class DockerProvider:
    def __init__(self, config: DockerSandboxConfig | None = None) -> None:
        self.config = config or DockerSandboxConfig()
        self._client: docker.DockerClient | None = None
        self._warm_pool: list[Container] = []
        self._pool_lock = asyncio.Lock()
        self._docker_available: bool | None = None
        self._image_built: bool = False

    @property
    def docker_available(self) -> bool:
        if self._docker_available is None:
            self._docker_available = _detect_docker_available()
        return self._docker_available

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            try:
                self._client = docker.from_env()
            except DockerException:
                raise DockerUnavailableError("Docker is not available")
        return self._client

    async def check_and_pull_image(self) -> None:
        if not self.docker_available:
            return

        try:
            local_image = self.client.images.get(DOCKER_IMAGE_FULL)
            local_version = local_image.labels.get("version", "")
        except ImageNotFound:
            local_version = ""

        if local_version != DOCKER_IMAGE_TAG:
            logger.info(
                f"Building sandbox image {DOCKER_IMAGE_FULL} (local version: {local_version or 'none'})"
            )
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.client.images.build(
                        path=str(SANDBOX_DOCKERFILE.parent),
                        dockerfile=str(SANDBOX_DOCKERFILE),
                        tag=DOCKER_IMAGE_FULL,
                        rm=True,
                    ),
                )
                self._image_built = True
                logger.info(f"Sandbox image {DOCKER_IMAGE_FULL} built successfully")
            except APIError as e:
                logger.error(f"Failed to build sandbox image: {e}")
                self._docker_available = False
                raise DockerUnavailableError(f"Failed to build sandbox image: {e}")

    async def initialize_warm_pool(self) -> None:
        if not self.docker_available:
            logger.info("Docker not available, skipping warm pool initialization")
            return

        await self.check_and_pull_image()

        async with self._pool_lock:
            for i in range(self.config.warm_pool_size):
                try:
                    container = await asyncio.get_running_loop().run_in_executor(
                        None,
                        self._create_idle_container,
                    )
                    self._warm_pool.append(container)
                    logger.debug(f"Warm pool container {i + 1}/{self.config.warm_pool_size} created")
                except Exception as e:
                    logger.warning(f"Failed to create warm pool container {i + 1}: {e}")

        logger.info(f"Warm pool initialized with {len(self._warm_pool)} containers")

    def _create_idle_container(self) -> Container:
        return self.client.containers.create(
            image=DOCKER_IMAGE_FULL,
            command=["sleep", "infinity"],
            network=self.config.network,
            mem_limit=self.config.memory,
            cpu_period=100000,
            cpu_quota=int(self.config.cpus * 100000),
            pids_limit=self.config.pids_limit,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            read_only=True,
            tmpfs={"/tmp": "size=256M,mode=1777"},
            detach=True,
        )

    async def _get_warm_container(self) -> Container:
        async with self._pool_lock:
            if self._warm_pool:
                container = self._warm_pool.pop()
                logger.debug(f"Reusing warm container {container.short_id}")
                return container

        logger.debug("Warm pool empty, creating new container")
        return await asyncio.get_running_loop().run_in_executor(
            None,
            self._create_idle_container,
        )

    async def _return_container(self, container: Container) -> None:
        async with self._pool_lock:
            if len(self._warm_pool) < self.config.warm_pool_size:
                try:
                    container.stop(timeout=1)
                    self._warm_pool.append(container)
                    logger.debug(f"Returned container {container.short_id} to pool")
                    return
                except Exception:
                    pass

        try:
            container.remove(force=True)
        except Exception:
            pass

    def _prepare_volumes(self, project_root: str, read_only: bool) -> dict[str, dict[str, str]]:
        host_path = _resolve_windows_volume(project_root)
        mode = "ro" if read_only else "rw"
        return {host_path: {"bind": DOCKER_WORKSPACE, "mode": mode}}

    def _build_docker_command(self, command: str, cwd: str = DOCKER_WORKSPACE) -> str:
        if cwd:
            return f"cd {shlex.quote(cwd)} && {command}"
        return command

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 120.0,
        project_root: str | None = None,
        read_only: bool = False,
    ) -> SandboxResult:
        if not self.docker_available:
            if os.environ.get("ALLOW_HOST_FALLBACK", "").lower() in ("1", "true"):
                return await self._execute_fallback(command, cwd, timeout)
            else:
                raise RuntimeError(
                    "Docker sandbox unavailable. Set ALLOW_HOST_FALLBACK=1 to fall back to host execution (insecure)."
                )

        try:
            container_cwd = cwd or DOCKER_WORKSPACE
            docker_command = self._build_docker_command(command, container_cwd)
            volumes = None
            if project_root:
                volumes = self._prepare_volumes(project_root, read_only)

            if read_only:
                container = await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self.client.containers.create(
                        image=DOCKER_IMAGE_FULL,
                        command=["/bin/bash", "-c", docker_command],
                        network=self.config.network,
                        mem_limit=self.config.memory,
                        cpu_period=100000,
                        cpu_quota=int(self.config.cpus * 100000),
                        pids_limit=self.config.pids_limit,
                        cap_drop=["ALL"],
                        security_opt=["no-new-privileges"],
                        read_only=True,
                        tmpfs={"/tmp": "size=256M,mode=1777"},
                        volumes=volumes,
                        detach=True,
                    ),
                )
            else:
                container = await self._get_warm_container()
                container.update(
                    command=["/bin/bash", "-c", docker_command],
                )

            try:
                loop = asyncio.get_running_loop()

                def _start_container() -> None:
                    container.start()

                await loop.run_in_executor(None, _start_container)

                def _wait_container() -> dict[str, Any]:
                    return container.wait()

                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, _wait_container),
                        timeout=timeout,
                    )
                    exit_code = result.get("StatusCode", -1)
                except asyncio.TimeoutError:
                    try:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(None, lambda: container.kill())
                    except Exception:
                        pass
                    raise SandboxTimeoutError(
                        f"Command timed out after {timeout}s: {command[:200]}"
                    )

                def _get_logs() -> bytes:
                    return container.logs(stdout=True, stderr=True)

                logs_binary = await loop.run_in_executor(None, _get_logs)
                all_output = logs_binary.decode("utf-8", errors="replace")

                stdout = all_output
                stderr = ""
                if "\x00" not in all_output:
                    stdout = all_output.strip()

                return SandboxResult(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                    timed_out=False,
                )

            finally:
                if read_only:
                    try:
                        await loop.run_in_executor(None, lambda: container.remove(force=True))
                    except Exception:
                        pass
                else:
                    await self._return_container(container)

        except (DockerException, APIError) as e:
            logger.warning(f"Docker execution failed: {e}")
            self._docker_available = False
            if os.environ.get("ALLOW_HOST_FALLBACK", "").lower() in ("1", "true"):
                return await self._execute_fallback(command, cwd, timeout)
            else:
                raise RuntimeError(
                    "Docker sandbox unavailable. Set ALLOW_HOST_FALLBACK=1 to fall back to host execution (insecure)."
                )

    async def _execute_fallback(
        self,
        command: str,
        cwd: str | None = None,
        timeout: float = 120.0,
    ) -> SandboxResult:
        logger.info(f"Executing command via host subprocess (fallback): {command[:200]}")

        try:
            working_dir = cwd or os.getcwd()
            if sys.platform == "win32":
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "/bin/bash", "-c", command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                return SandboxResult(
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    exit_code=proc.returncode or 0,
                    timed_out=False,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                raise SandboxTimeoutError(
                    f"Command timed out after {timeout}s (fallback): {command[:200]}"
                )
        except FileNotFoundError as e:
            return SandboxResult(
                stdout="",
                stderr=f"Command not found: {e}",
                exit_code=127,
            )

    async def cleanup(self) -> None:
        async with self._pool_lock:
            for container in self._warm_pool:
                try:
                    await asyncio.get_running_loop().run_in_executor(
                        None, lambda c=container: c.remove(force=True)
                    )
                except Exception:
                    pass
            self._warm_pool.clear()
            logger.info("Warm pool cleaned up")

        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


_sandbox_provider: DockerProvider | None = None


def get_sandbox_provider() -> DockerProvider:
    global _sandbox_provider
    if _sandbox_provider is None:
        _sandbox_provider = DockerProvider()
    return _sandbox_provider


async def initialize_sandbox() -> None:
    provider = get_sandbox_provider()
    await provider.initialize_warm_pool()


async def cleanup_sandbox() -> None:
    global _sandbox_provider
    if _sandbox_provider is not None:
        await _sandbox_provider.cleanup()
        _sandbox_provider = None


def is_docker_available() -> bool:
    provider = get_sandbox_provider()
    return provider.docker_available


def reset_sandbox_for_testing() -> None:
    global _sandbox_provider
    _sandbox_provider = None
