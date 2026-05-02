from __future__ import annotations

import pytest
from server.prompts.system import (
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    _get_git_section,
    _get_language_section,
    assemble_system_prompt,
    get_system_prompt,
)


class TestSystemPrompt:
    def test_boundary_constant(self):
        assert SYSTEM_PROMPT_DYNAMIC_BOUNDARY == "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"

    def test_get_system_prompt_returns_list(self):
        sections = get_system_prompt(
            tools=[],
            model="test-model",
        )
        assert isinstance(sections, list)
        assert len(sections) > 0

    def test_assemble_system_prompt(self):
        sections = ["# Section A", "# Section B", "# Section C"]
        result = assemble_system_prompt(sections)
        assert "# Section A" in result
        assert "# Section B" in result
        assert "\n\n" in result

    def test_language_section(self):
        section = _get_language_section("Chinese")
        assert section is not None
        assert "Chinese" in section

    def test_language_section_none(self):
        section = _get_language_section(None)
        assert section is None

    def test_git_section(self):
        section = _get_git_section("Current branch: main\nStatus: clean")
        assert section is not None
        assert "Current branch: main" in section

    def test_git_section_none(self):
        section = _get_git_section(None)
        assert section is None

    def test_git_status_in_prompt(self):
        sections = get_system_prompt(
            tools=[],
            model="test-model",
            git_status="Current branch: main\nStatus: clean",
        )
        prompt = assemble_system_prompt(sections)
        assert "Current branch: main" in prompt
