from __future__ import annotations

import pytest

from server.commands.pipeline import dispatch_command, handle_slash_command, is_slash_command


class TestCommandPipeline:
    def test_is_slash_command(self):
        assert is_slash_command("/help")
        assert is_slash_command("/model sonnet")
        assert not is_slash_command("hello")
        assert not is_slash_command("")

    def test_handle_slash_command_help(self):
        result = handle_slash_command("/help")
        assert result is not None
        assert result["command"] == "help"
        assert result["type"] == "local"

    def test_handle_slash_command_model(self):
        result = handle_slash_command("/model sonnet")
        assert result is not None
        assert result["command"] == "model"
        assert result["args"] == "sonnet"

    def test_handle_slash_command_unknown(self):
        result = handle_slash_command("/unknown_cmd")
        assert result is None

    def test_dispatch_command(self):
        result = dispatch_command("/clear")
        assert result is not None
        assert result["command"] == "clear"
