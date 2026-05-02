from __future__ import annotations

import pytest
from pydantic import BaseModel


class PermissionResult(BaseModel):
    behavior: str = "allow"
    updated_input: dict | None = None
    message: str = ""


class TestPermissionResult:
    def test_allow(self):
        r = PermissionResult(behavior="allow")
        assert r.behavior == "allow"

    def test_deny(self):
        r = PermissionResult(behavior="deny", message="Blocked for security")
        assert r.message == "Blocked for security"

    def test_ask(self):
        r = PermissionResult(behavior="ask")
        assert r.behavior == "ask"

    def test_passthrough(self):
        r = PermissionResult(behavior="passthrough")
        assert r.behavior == "passthrough"


class TestPermissionModes:
    def test_all_modes(self):
        modes = {"default", "accept_edits", "bypass", "dont_ask", "plan", "auto", "bubble"}
        assert len(modes) == 7
