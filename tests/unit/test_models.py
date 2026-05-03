from __future__ import annotations

import pytest
from server.models.permissions import PermissionMode


class TestPermissionMode:
    def test_default_mode(self):
        assert PermissionMode.DEFAULT.value == "default"

    def test_accept_edits(self):
        assert PermissionMode.ACCEPT_EDITS.value == "acceptEdits"

    def test_bypass(self):
        assert PermissionMode.BYPASS_PERMISSIONS.value == "bypassPermissions"

    def test_dont_ask(self):
        assert PermissionMode.DONT_ASK.value == "dontAsk"

    def test_plan_mode(self):
        assert PermissionMode.PLAN.value == "plan"

    def test_auto_mode(self):
        assert PermissionMode.AUTO.value == "auto"

    def test_bubble_mode(self):
        assert PermissionMode.BUBBLE.value == "bubble"
