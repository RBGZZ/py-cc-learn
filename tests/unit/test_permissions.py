from __future__ import annotations

import pytest


class TestPermissionResult:
    def test_allow_behavior(self):
        from server.tools.tool import PermissionResult
        pr = PermissionResult(behavior="allow", updated_input={"cmd": "ls"})
        assert pr.behavior == "allow"
        assert pr.updated_input == {"cmd": "ls"}

    def test_deny_behavior(self):
        from server.tools.tool import PermissionResult
        pr = PermissionResult(behavior="deny", message="not allowed")
        assert pr.behavior == "deny"

    def test_passthrough_behavior(self):
        from server.tools.tool import PermissionResult
        pr = PermissionResult(behavior="passthrough")
        assert pr.behavior == "passthrough"

    def test_ask_default(self):
        from server.tools.tool import PermissionResult
        pr = PermissionResult()
        assert pr.behavior == "allow"
