from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AppState(BaseModel):
    session_id: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    is_processing: bool = False
    current_model: str = ""
    permission_mode: str = "default"
    total_cost_usd: float = 0.0
    context_tokens: int = 0
    context_limit: int = 200000
    todos: Dict[str, Any] = Field(default_factory=dict)
    tasks: Dict[str, Any] = Field(default_factory=dict)
    mcp_tools: List[Dict[str, Any]] = Field(default_factory=list)
    mcp_clients: List[Dict[str, Any]] = Field(default_factory=list)
    notifications: List[Dict[str, Any]] = Field(default_factory=list)
    expanded_view: str = "none"
    status_line_text: Optional[str] = None
    spinner_tip: Optional[str] = None
    is_interactive: bool = False
    has_exited_plan_mode: bool = False
    needs_plan_mode_exit_attachment: bool = False
    verbose: bool = False
    sdk_status: Optional[str] = None


_default_app_state = AppState()


def get_default_app_state() -> AppState:
    return _default_app_state.model_copy()
