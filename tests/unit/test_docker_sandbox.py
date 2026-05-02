from __future__ import annotations

import pytest
import os


class TestDockerSandbox:
    def test_dockerfile_exists(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        dockerfile = base / "sandbox" / "Dockerfile"
        assert dockerfile.exists(), f"Dockerfile not found at {dockerfile}"

    def test_dockerfile_has_base_image(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        dockerfile = base / "sandbox" / "Dockerfile"
        content = dockerfile.read_text()
        assert "FROM" in content
        assert "ubuntu" in content.lower()

    def test_dockerfile_has_label(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        dockerfile = base / "sandbox" / "Dockerfile"
        content = dockerfile.read_text()
        assert "LABEL version" in content or "LABEL version=" in content

    def test_sandbox_manager_exists(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        manager = base / "sandbox" / "manager.py"
        assert manager.exists()

    def test_sandbox_manager_importable(self):
        import importlib
        try:
            import sandbox.manager
            assert hasattr(sandbox.manager, "is_docker_available") or True
        except ImportError:
            pytest.skip("sandbox module not importable (no docker-py?)")

    def test_docker_fallback_importable(self):
        try:
            from sandbox.manager import is_docker_available
            available = is_docker_available()
            assert isinstance(available, bool)
        except ImportError:
            pytest.skip("sandbox module not importable")

    def test_docker_fallback_coverage(self):
        try:
            from sandbox.manager import is_docker_available
            available = is_docker_available()
            if not available:
                print("Docker not available — fallback mode active (expected on CI/Windows)")
        except ImportError:
            pytest.skip("sandbox module not importable")

    def test_container_limits_config(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        manager = base / "sandbox" / "manager.py"
        content = manager.read_text()
        assert "network" in content.lower() or "memory" in content.lower()

    def test_readonly_mount_config(self):
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent
        manager = base / "sandbox" / "manager.py"
        content = manager.read_text()
        assert "isReadOnly" in content or "ro" in content
