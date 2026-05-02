from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any, Dict, List, Optional, Set

SCROLL_DRAIN_IDLE_MS = 150
MAX_IN_MEMORY_ERRORS = 100
MAX_SLOW_OPERATIONS = 10
SLOW_OPERATION_TTL_MS = 10000


class ChannelEntry:
    def __init__(self, kind: str, name: str, marketplace: str = "", dev: bool = False):
        self.kind = kind
        self.name = name
        self.marketplace = marketplace
        self.dev = dev


class SessionCronTask:
    def __init__(
        self,
        id: str,
        cron: str,
        prompt: str,
        created_at: int,
        recurring: bool = False,
        agent_id: Optional[str] = None,
    ):
        self.id = id
        self.cron = cron
        self.prompt = prompt
        self.created_at = created_at
        self.recurring = recurring
        self.agent_id = agent_id


class InvokedSkillInfo:
    def __init__(
        self,
        skill_name: str,
        skill_path: str,
        content: str,
        invoked_at: int,
        agent_id: Optional[str] = None,
    ):
        self.skill_name = skill_name
        self.skill_path = skill_path
        self.content = content
        self.invoked_at = invoked_at
        self.agent_id = agent_id


class SlowOperation:
    def __init__(self, operation: str, duration_ms: int, timestamp: int):
        self.operation = operation
        self.duration_ms = duration_ms
        self.timestamp = timestamp


class TeleportedSessionInfo:
    def __init__(self, is_teleported: bool = False, has_logged_first_message: bool = False, session_id: Optional[str] = None):
        self.is_teleported = is_teleported
        self.has_logged_first_message = has_logged_first_message
        self.session_id = session_id


class GlobalState:
    _instance: Optional[GlobalState] = None
    _lock = threading.Lock()

    def __init__(self):
        if GlobalState._instance is not None:
            raise RuntimeError("GlobalState is a singleton. Use get_instance()")
        self._reset_fields()
        self._session_switched_callbacks: List[Callable[[str], None]] = []
        self._scroll_draining = False
        self._scroll_drain_timer: Any = None
        self._interaction_time_dirty = False
        self._output_tokens_at_turn_start = 0
        self._current_turn_token_budget: Optional[int] = None
        self._budget_continuation_count = 0

    def _reset_fields(self):
        resolved_cwd = os.path.normpath(os.getcwd())
        now_ms = int(time.time() * 1000)
        now_ts = time.time()

        self.original_cwd: str = resolved_cwd
        self.project_root: str = resolved_cwd
        self.total_cost_usd: float = 0.0
        self.total_api_duration: float = 0.0
        self.total_api_duration_without_retries: float = 0.0
        self.total_tool_duration: float = 0.0
        self.turn_hook_duration_ms: float = 0.0
        self.turn_tool_duration_ms: float = 0.0
        self.turn_classifier_duration_ms: float = 0.0
        self.turn_tool_count: int = 0
        self.turn_hook_count: int = 0
        self.turn_classifier_count: int = 0
        self.start_time: float = now_ts
        self.last_interaction_time: float = now_ts
        self.total_lines_added: int = 0
        self.total_lines_removed: int = 0
        self.has_unknown_model_cost: bool = False
        self.cwd: str = resolved_cwd
        self.model_usage: Dict[str, Dict[str, Any]] = {}
        self.main_loop_model_override: Optional[Dict[str, Any]] = None
        self.initial_main_loop_model: Optional[Dict[str, Any]] = None
        self.model_strings: Optional[Any] = None
        self.is_interactive: bool = False
        self.kairos_active: bool = False
        self.strict_tool_result_pairing: bool = False
        self.sdk_agent_progress_summaries_enabled: bool = False
        self.user_msg_opt_in: bool = False
        self.client_type: str = "cli"
        self.session_source: Optional[str] = None
        self.question_preview_format: Optional[str] = None
        self.flag_settings_path: Optional[str] = None
        self.flag_settings_inline: Optional[Dict[str, Any]] = None
        self.allowed_setting_sources: List[str] = [
            "userSettings",
            "projectSettings",
            "localSettings",
            "flagSettings",
            "policySettings",
        ]
        self.session_ingress_token: Optional[str] = None
        self.oauth_token_from_fd: Optional[str] = None
        self.api_key_from_fd: Optional[str] = None
        self.meter: Any = None
        self.session_counter: Any = None
        self.loc_counter: Any = None
        self.pr_counter: Any = None
        self.commit_counter: Any = None
        self.cost_counter: Any = None
        self.token_counter: Any = None
        self.code_edit_tool_decision_counter: Any = None
        self.active_time_counter: Any = None
        self.stats_store: Optional[Any] = None
        self.session_id: str = str(uuid.uuid4())
        self.parent_session_id: Optional[str] = None
        self.logger_provider: Any = None
        self.event_logger: Any = None
        self.meter_provider: Any = None
        self.tracer_provider: Any = None
        self.agent_color_map: Dict[str, Any] = {}
        self.agent_color_index: int = 0
        self.last_api_request: Optional[Dict[str, Any]] = None
        self.last_api_request_messages: Optional[List[Any]] = None
        self.last_classifier_requests: Optional[List[Any]] = None
        self.cached_claude_md_content: Optional[str] = None
        self.in_memory_error_log: List[Dict[str, str]] = []
        self.inline_plugins: List[str] = []
        self.chrome_flag_override: Optional[bool] = None
        self.use_cowork_plugins: bool = False
        self.session_bypass_permissions_mode: bool = False
        self.scheduled_tasks_enabled: bool = False
        self.session_cron_tasks: List[SessionCronTask] = []
        self.session_created_teams: Set[str] = set()
        self.session_trust_accepted: bool = False
        self.session_persistence_disabled: bool = False
        self.has_exited_plan_mode: bool = False
        self.needs_plan_mode_exit_attachment: bool = False
        self.needs_auto_mode_exit_attachment: bool = False
        self.lsp_recommendation_shown_this_session: bool = False
        self.init_json_schema: Optional[Dict[str, Any]] = None
        self.registered_hooks: Optional[Dict[str, List[Any]]] = None
        self.plan_slug_cache: Dict[str, str] = {}
        self.teleported_session_info: Optional[TeleportedSessionInfo] = None
        self.invoked_skills: Dict[str, InvokedSkillInfo] = {}
        self.slow_operations: List[SlowOperation] = []
        self.sdk_betas: Optional[List[str]] = None
        self.main_thread_agent_type: Optional[str] = None
        self.is_remote_mode: bool = False
        self.direct_connect_server_url: Optional[str] = None
        self.system_prompt_section_cache: Dict[str, Optional[str]] = {}
        self.last_emitted_date: Optional[str] = None
        self.additional_directories_for_claude_md: List[str] = []
        self.allowed_channels: List[ChannelEntry] = []
        self.has_dev_channels: bool = False
        self.session_project_dir: Optional[str] = None
        self.prompt_cache_1h_allowlist: Optional[List[str]] = None
        self.prompt_cache_1h_eligible: Optional[bool] = None
        self.afk_mode_header_latched: Optional[bool] = None
        self.fast_mode_header_latched: Optional[bool] = None
        self.cache_editing_header_latched: Optional[bool] = None
        self.thinking_clear_latched: Optional[bool] = None
        self.prompt_id: Optional[str] = None
        self.last_main_request_id: Optional[str] = None
        self.last_api_completion_timestamp: Optional[int] = None
        self.pending_post_compaction: bool = False

    @classmethod
    def get_instance(cls) -> GlobalState:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance_for_tests(cls) -> GlobalState:
        with cls._lock:
            cls._instance = cls()
            return cls._instance

    def initialize(self):
        pass

    def shutdown(self):
        pass

    def get_uptime_seconds(self) -> float:
        return time.time() - self.start_time

    def regenerate_session_id(self, set_current_as_parent: bool = False) -> str:
        if set_current_as_parent:
            self.parent_session_id = self.session_id
        self.plan_slug_cache.pop(self.session_id, None)
        self.session_id = str(uuid.uuid4())
        self.session_project_dir = None
        self._session_switched_emit(self.session_id)
        return self.session_id

    def switch_session(self, session_id: str, project_dir: Optional[str] = None):
        self.plan_slug_cache.pop(self.session_id, None)
        self.session_id = session_id
        self.session_project_dir = project_dir
        self._session_switched_emit(session_id)

    def _session_switched_emit(self, session_id: str):
        for cb in self._session_switched_callbacks:
            try:
                cb(session_id)
            except Exception:
                pass

    def on_session_switch(self, callback: Callable[[str], None]):
        self._session_switched_callbacks.append(callback)

    def add_to_total_duration(self, duration: float, duration_without_retries: float):
        self.total_api_duration += duration
        self.total_api_duration_without_retries += duration_without_retries

    def add_to_total_cost(self, cost: float, model_usage: Dict[str, Any], model: str):
        self.model_usage[model] = model_usage
        self.total_cost_usd += cost

    def add_to_tool_duration(self, duration: float):
        self.total_tool_duration += duration
        self.turn_tool_duration_ms += duration
        self.turn_tool_count += 1

    def add_to_turn_hook_duration(self, duration: float):
        self.turn_hook_duration_ms += duration
        self.turn_hook_count += 1

    def reset_turn_hook_duration(self):
        self.turn_hook_duration_ms = 0.0
        self.turn_hook_count = 0

    def reset_turn_tool_duration(self):
        self.turn_tool_duration_ms = 0.0
        self.turn_tool_count = 0

    def add_to_turn_classifier_duration(self, duration: float):
        self.turn_classifier_duration_ms += duration
        self.turn_classifier_count += 1

    def reset_turn_classifier_duration(self):
        self.turn_classifier_duration_ms = 0.0
        self.turn_classifier_count = 0

    def update_last_interaction_time(self, immediate: bool = False):
        if immediate:
            self._flush_interaction_time()
        else:
            self._interaction_time_dirty = True

    def flush_interaction_time(self):
        if self._interaction_time_dirty:
            self._flush_interaction_time()

    def _flush_interaction_time(self):
        self.last_interaction_time = time.time()
        self._interaction_time_dirty = False

    def add_to_total_lines_changed(self, added: int, removed: int):
        self.total_lines_added += added
        self.total_lines_removed += removed

    def get_total_input_tokens(self) -> int:
        return sum(u.get("inputTokens", 0) for u in self.model_usage.values())

    def get_total_output_tokens(self) -> int:
        return sum(u.get("outputTokens", 0) for u in self.model_usage.values())

    def get_total_cache_read_input_tokens(self) -> int:
        return sum(u.get("cacheReadInputTokens", 0) for u in self.model_usage.values())

    def get_total_cache_creation_input_tokens(self) -> int:
        return sum(u.get("cacheCreationInputTokens", 0) for u in self.model_usage.values())

    def get_total_web_search_requests(self) -> int:
        return sum(u.get("webSearchRequests", 0) for u in self.model_usage.values())

    def get_turn_output_tokens(self) -> int:
        return self.get_total_output_tokens() - self._output_tokens_at_turn_start

    def get_current_turn_token_budget(self) -> Optional[int]:
        return self._current_turn_token_budget

    def snapshot_output_tokens_for_turn(self, budget: Optional[int] = None):
        self._output_tokens_at_turn_start = self.get_total_output_tokens()
        self._current_turn_token_budget = budget
        self._budget_continuation_count = 0

    def get_budget_continuation_count(self) -> int:
        return self._budget_continuation_count

    def increment_budget_continuation_count(self):
        self._budget_continuation_count += 1

    def get_total_duration(self) -> float:
        return time.time() - self.start_time

    def mark_post_compaction(self):
        self.pending_post_compaction = True

    def consume_post_compaction(self) -> bool:
        was = self.pending_post_compaction
        self.pending_post_compaction = False
        return was

    def add_to_in_memory_error_log(self, error_info: Dict[str, str]):
        if len(self.in_memory_error_log) >= MAX_IN_MEMORY_ERRORS:
            self.in_memory_error_log.pop(0)
        self.in_memory_error_log.append(error_info)

    def add_invoked_skill(self, skill_name: str, skill_path: str, content: str, agent_id: Optional[str] = None):
        key = f"{agent_id or ''}:{skill_name}"
        self.invoked_skills[key] = InvokedSkillInfo(
            skill_name=skill_name,
            skill_path=skill_path,
            content=content,
            invoked_at=int(time.time() * 1000),
            agent_id=agent_id,
        )

    def get_invoked_skills_for_agent(self, agent_id: Optional[str]) -> Dict[str, InvokedSkillInfo]:
        normalized_id = agent_id
        result: Dict[str, InvokedSkillInfo] = {}
        for key, skill in self.invoked_skills.items():
            if skill.agent_id == normalized_id:
                result[key] = skill
        return result

    def add_slow_operation(self, operation: str, duration_ms: int):
        if os.environ.get("USER_TYPE") != "ant":
            return
        if "exec" in operation and "claude-prompt-" in operation:
            return
        now = int(time.time() * 1000)
        self.slow_operations = [
            op for op in self.slow_operations if now - op.timestamp < SLOW_OPERATION_TTL_MS
        ]
        self.slow_operations.append(SlowOperation(operation=operation, duration_ms=duration_ms, timestamp=now))
        if len(self.slow_operations) > MAX_SLOW_OPERATIONS:
            self.slow_operations = self.slow_operations[-MAX_SLOW_OPERATIONS:]

    def get_is_scroll_draining(self) -> bool:
        return self._scroll_draining

    def set_cost_state_for_restore(
        self,
        total_cost_usd: float,
        total_api_duration: float,
        total_api_duration_without_retries: float,
        total_tool_duration: float,
        total_lines_added: int,
        total_lines_removed: int,
        last_duration: Optional[float],
        model_usage: Optional[Dict[str, Any]],
    ):
        self.total_cost_usd = total_cost_usd
        self.total_api_duration = total_api_duration
        self.total_api_duration_without_retries = total_api_duration_without_retries
        self.total_tool_duration = total_tool_duration
        self.total_lines_added = total_lines_added
        self.total_lines_removed = total_lines_removed
        if model_usage:
            self.model_usage = model_usage
        if last_duration:
            self.start_time = time.time() - last_duration

    def reset_cost_state(self):
        self.total_cost_usd = 0.0
        self.total_api_duration = 0.0
        self.total_api_duration_without_retries = 0.0
        self.total_tool_duration = 0.0
        self.start_time = time.time()
        self.total_lines_added = 0
        self.total_lines_removed = 0
        self.has_unknown_model_cost = False
        self.model_usage = {}
        self.prompt_id = None

    def clear_beta_header_latches(self):
        self.afk_mode_header_latched = None
        self.fast_mode_header_latched = None
        self.cache_editing_header_latched = None
        self.thinking_clear_latched = None

    def clear_registered_hooks(self):
        self.registered_hooks = None

    def clear_invoked_skills(self, preserved_agent_ids: Optional[Set[str]] = None):
        if not preserved_agent_ids:
            self.invoked_skills.clear()
            return
        keys_to_delete = []
        for key, skill in self.invoked_skills.items():
            if skill.agent_id is None or skill.agent_id not in preserved_agent_ids:
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del self.invoked_skills[key]

    def add_session_cron_task(self, task: SessionCronTask):
        self.session_cron_tasks.append(task)

    def remove_session_cron_tasks(self, ids: List[str]) -> int:
        if not ids:
            return 0
        id_set = set(ids)
        remaining = [t for t in self.session_cron_tasks if t.id not in id_set]
        removed = len(self.session_cron_tasks) - len(remaining)
        if removed == 0:
            return 0
        self.session_cron_tasks = remaining
        return removed

    def handle_plan_mode_transition(self, from_mode: str, to_mode: str):
        if to_mode == "plan" and from_mode != "plan":
            self.needs_plan_mode_exit_attachment = False
        if from_mode == "plan" and to_mode != "plan":
            self.needs_plan_mode_exit_attachment = True

    def handle_auto_mode_transition(self, from_mode: str, to_mode: str):
        if (from_mode == "auto" and to_mode == "plan") or (from_mode == "plan" and to_mode == "auto"):
            return
        from_is_auto = from_mode == "auto"
        to_is_auto = to_mode == "auto"
        if to_is_auto and not from_is_auto:
            self.needs_auto_mode_exit_attachment = False
        if from_is_auto and not to_is_auto:
            self.needs_auto_mode_exit_attachment = True
