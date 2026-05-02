from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppState(BaseModel):
    session_id: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    is_processing: bool = False
    current_model: str = ""
    permission_mode: str = "default"
    total_cost_usd: float = 0.0
    context_tokens: int = 0
    context_limit: int = 200000
    todos: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, Any] = Field(default_factory=dict)
    mcp_tools: list[dict[str, Any]] = Field(default_factory=list)
    mcp_clients: list[dict[str, Any]] = Field(default_factory=list)
    notifications: list[dict[str, Any]] = Field(default_factory=list)
    expanded_view: str = "none"
    status_line_text: str | None = None
    spinner_tip: str | None = None
    is_interactive: bool = False
    has_exited_plan_mode: bool = False
    needs_plan_mode_exit_attachment: bool = False
    verbose: bool = False
    sdk_status: str | None = None


_default_app_state = AppState()


def get_default_app_state() -> AppState:
    return _default_app_state.model_copy()
