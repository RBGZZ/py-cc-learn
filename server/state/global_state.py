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

    # ============================================================================
    # Singleton access
    # ============================================================================

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

    # ============================================================================
    # Session ID
    # ============================================================================

    def get_session_id(self) -> str:
        return self.session_id

    def regenerate_session_id(self, set_current_as_parent: bool = False) -> str:
        if set_current_as_parent:
            self.parent_session_id = self.session_id
        self.plan_slug_cache.pop(self.session_id, None)
        self.session_id = str(uuid.uuid4())
        self.session_project_dir = None
        self._session_switched_emit(self.session_id)
        return self.session_id

    def get_parent_session_id(self) -> Optional[str]:
        return self.parent_session_id

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

    def get_session_project_dir(self) -> Optional[str]:
        return self.session_project_dir

    # ============================================================================
    # CWD / Project Root
    # ============================================================================

    def get_original_cwd(self) -> str:
        return self.original_cwd

    def set_original_cwd(self, cwd: str):
        self.original_cwd = cwd

    def get_project_root(self) -> str:
        return self.project_root

    def set_project_root(self, cwd: str):
        self.project_root = cwd

    def get_cwd_state(self) -> str:
        return self.cwd

    def set_cwd_state(self, cwd: str):
        self.cwd = cwd

    def get_direct_connect_server_url(self) -> Optional[str]:
        return self.direct_connect_server_url

    def set_direct_connect_server_url(self, url: str):
        self.direct_connect_server_url = url

    # ============================================================================
    # Duration / Cost
    # ============================================================================

    def add_to_total_duration(self, duration: float, duration_without_retries: float):
        self.total_api_duration += duration
        self.total_api_duration_without_retries += duration_without_retries

    def get_total_api_duration(self) -> float:
        return self.total_api_duration

    def get_total_api_duration_without_retries(self) -> float:
        return self.total_api_duration_without_retries

    def add_to_total_cost(self, cost: float, model_usage: Dict[str, Any], model: str):
        self.model_usage[model] = model_usage
        self.total_cost_usd += cost

    def get_total_cost_usd(self) -> float:
        return self.total_cost_usd

    def get_total_duration(self) -> float:
        return time.time() - self.start_time

    def get_total_tool_duration(self) -> float:
        return self.total_tool_duration

    def add_to_tool_duration(self, duration: float):
        self.total_tool_duration += duration
        self.turn_tool_duration_ms += duration
        self.turn_tool_count += 1

    def get_turn_hook_duration_ms(self) -> float:
        return self.turn_hook_duration_ms

    def add_to_turn_hook_duration(self, duration: float):
        self.turn_hook_duration_ms += duration
        self.turn_hook_count += 1

    def reset_turn_hook_duration(self):
        self.turn_hook_duration_ms = 0.0
        self.turn_hook_count = 0

    def get_turn_hook_count(self) -> int:
        return self.turn_hook_count

    def get_turn_tool_duration_ms(self) -> float:
        return self.turn_tool_duration_ms

    def reset_turn_tool_duration(self):
        self.turn_tool_duration_ms = 0.0
        self.turn_tool_count = 0

    def get_turn_tool_count(self) -> int:
        return self.turn_tool_count

    def get_turn_classifier_duration_ms(self) -> float:
        return self.turn_classifier_duration_ms

    def add_to_turn_classifier_duration(self, duration: float):
        self.turn_classifier_duration_ms += duration
        self.turn_classifier_count += 1

    def reset_turn_classifier_duration(self):
        self.turn_classifier_duration_ms = 0.0
        self.turn_classifier_count = 0

    def get_turn_classifier_count(self) -> int:
        return self.turn_classifier_count

    def get_stats_store(self) -> Optional[Any]:
        return self.stats_store

    def set_stats_store(self, store: Optional[Any]):
        self.stats_store = store

    # ============================================================================
    # Interaction Time
    # ============================================================================

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

    def get_last_interaction_time(self) -> float:
        return self.last_interaction_time

    # ============================================================================
    # Lines Changed
    # ============================================================================

    def add_to_total_lines_changed(self, added: int, removed: int):
        self.total_lines_added += added
        self.total_lines_removed += removed

    def get_total_lines_added(self) -> int:
        return self.total_lines_added

    def get_total_lines_removed(self) -> int:
        return self.total_lines_removed

    # ============================================================================
    # Token Counting
    # ============================================================================

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

    # ============================================================================
    # Unknown Model Cost
    # ============================================================================

    def set_has_unknown_model_cost(self):
        self.has_unknown_model_cost = True

    def has_unknown_model_cost_flag(self) -> bool:
        return self.has_unknown_model_cost

    # ============================================================================
    # Last Request Tracking
    # ============================================================================

    def get_last_main_request_id(self) -> Optional[str]:
        return self.last_main_request_id

    def set_last_main_request_id(self, request_id: str):
        self.last_main_request_id = request_id

    def get_last_api_completion_timestamp(self) -> Optional[int]:
        return self.last_api_completion_timestamp

    def set_last_api_completion_timestamp(self, timestamp: int):
        self.last_api_completion_timestamp = timestamp

    # ============================================================================
    # Compaction
    # ============================================================================

    def mark_post_compaction(self):
        self.pending_post_compaction = True

    def consume_post_compaction(self) -> bool:
        was = self.pending_post_compaction
        self.pending_post_compaction = False
        return was

    # ============================================================================
    # Scroll Drain
    # ============================================================================

    def get_is_scroll_draining(self) -> bool:
        return self._scroll_draining

    # ============================================================================
    # Model Usage
    # ============================================================================

    def get_model_usage(self) -> Dict[str, Dict[str, Any]]:
        return self.model_usage

    def get_usage_for_model(self, model: str) -> Optional[Dict[str, Any]]:
        return self.model_usage.get(model)

    def get_main_loop_model_override(self) -> Optional[Dict[str, Any]]:
        return self.main_loop_model_override

    def get_initial_main_loop_model(self) -> Optional[Dict[str, Any]]:
        return self.initial_main_loop_model

    def set_main_loop_model_override(self, model: Optional[Dict[str, Any]]):
        self.main_loop_model_override = model

    def set_initial_main_loop_model(self, model: Dict[str, Any]):
        self.initial_main_loop_model = model

    def get_model_strings(self) -> Optional[Any]:
        return self.model_strings

    def set_model_strings(self, model_strings: Any):
        self.model_strings = model_strings

    # ============================================================================
    # SDK Betas
    # ============================================================================

    def get_sdk_betas(self) -> Optional[List[str]]:
        return self.sdk_betas

    def set_sdk_betas(self, betas: Optional[List[str]]):
        self.sdk_betas = betas

    # ============================================================================
    # Cost State
    # ============================================================================

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

    # ============================================================================
    # Meter / Counters
    # ============================================================================

    def get_meter(self) -> Any:
        return self.meter

    def get_session_counter(self) -> Any:
        return self.session_counter

    def get_loc_counter(self) -> Any:
        return self.loc_counter

    def get_pr_counter(self) -> Any:
        return self.pr_counter

    def get_commit_counter(self) -> Any:
        return self.commit_counter

    def get_cost_counter(self) -> Any:
        return self.cost_counter

    def get_token_counter(self) -> Any:
        return self.token_counter

    def get_code_edit_tool_decision_counter(self) -> Any:
        return self.code_edit_tool_decision_counter

    def get_active_time_counter(self) -> Any:
        return self.active_time_counter

    # ============================================================================
    # Logger / Meter / Tracer Providers
    # ============================================================================

    def get_logger_provider(self) -> Any:
        return self.logger_provider

    def set_logger_provider(self, provider: Any):
        self.logger_provider = provider

    def get_event_logger(self) -> Any:
        return self.event_logger

    def set_event_logger(self, logger: Any):
        self.event_logger = logger

    def get_meter_provider(self) -> Any:
        return self.meter_provider

    def set_meter_provider(self, provider: Any):
        self.meter_provider = provider

    def get_tracer_provider(self) -> Any:
        return self.tracer_provider

    def set_tracer_provider(self, provider: Any):
        self.tracer_provider = provider

    # ============================================================================
    # Interactive / Client
    # ============================================================================

    def get_is_non_interactive_session(self) -> bool:
        return not self.is_interactive

    def get_is_interactive(self) -> bool:
        return self.is_interactive

    def set_is_interactive(self, value: bool):
        self.is_interactive = value

    def get_client_type(self) -> str:
        return self.client_type

    def set_client_type(self, client_type: str):
        self.client_type = client_type

    # ============================================================================
    # Feature flags
    # ============================================================================

    def get_sdk_agent_progress_summaries_enabled(self) -> bool:
        return self.sdk_agent_progress_summaries_enabled

    def set_sdk_agent_progress_summaries_enabled(self, value: bool):
        self.sdk_agent_progress_summaries_enabled = value

    def get_kairos_active(self) -> bool:
        return self.kairos_active

    def set_kairos_active(self, value: bool):
        self.kairos_active = value

    def get_strict_tool_result_pairing(self) -> bool:
        return self.strict_tool_result_pairing

    def set_strict_tool_result_pairing(self, value: bool):
        self.strict_tool_result_pairing = value

    def get_user_msg_opt_in(self) -> bool:
        return self.user_msg_opt_in

    def set_user_msg_opt_in(self, value: bool):
        self.user_msg_opt_in = value

    # ============================================================================
    # Session Source / Preview Format
    # ============================================================================

    def get_session_source(self) -> Optional[str]:
        return self.session_source

    def set_session_source(self, source: str):
        self.session_source = source

    def get_question_preview_format(self) -> Optional[str]:
        return self.question_preview_format

    def set_question_preview_format(self, fmt: str):
        self.question_preview_format = fmt

    # ============================================================================
    # Agent Colors
    # ============================================================================

    def get_agent_color_map(self) -> Dict[str, Any]:
        return self.agent_color_map

    def get_agent_color_index(self) -> int:
        return self.agent_color_index

    # ============================================================================
    # Flag Settings
    # ============================================================================

    def get_flag_settings_path(self) -> Optional[str]:
        return self.flag_settings_path

    def set_flag_settings_path(self, path: Optional[str]):
        self.flag_settings_path = path

    def get_flag_settings_inline(self) -> Optional[Dict[str, Any]]:
        return self.flag_settings_inline

    def set_flag_settings_inline(self, settings: Optional[Dict[str, Any]]):
        self.flag_settings_inline = settings

    # ============================================================================
    # Tokens / Keys
    # ============================================================================

    def get_session_ingress_token(self) -> Optional[str]:
        return self.session_ingress_token

    def set_session_ingress_token(self, token: Optional[str]):
        self.session_ingress_token = token

    def get_oauth_token_from_fd(self) -> Optional[str]:
        return self.oauth_token_from_fd

    def set_oauth_token_from_fd(self, token: Optional[str]):
        self.oauth_token_from_fd = token

    def get_api_key_from_fd(self) -> Optional[str]:
        return self.api_key_from_fd

    def set_api_key_from_fd(self, key: Optional[str]):
        self.api_key_from_fd = key

    # ============================================================================
    # Last API Request
    # ============================================================================

    def set_last_api_request(self, params: Optional[Dict[str, Any]]):
        self.last_api_request = params

    def get_last_api_request(self) -> Optional[Dict[str, Any]]:
        return self.last_api_request

    def set_last_api_request_messages(self, messages: Optional[List[Any]]):
        self.last_api_request_messages = messages

    def get_last_api_request_messages(self) -> Optional[List[Any]]:
        return self.last_api_request_messages

    def set_last_classifier_requests(self, requests: Optional[List[Any]]):
        self.last_classifier_requests = requests

    def get_last_classifier_requests(self) -> Optional[List[Any]]:
        return self.last_classifier_requests

    # ============================================================================
    # Claude.md Cache
    # ============================================================================

    def set_cached_claude_md_content(self, content: Optional[str]):
        self.cached_claude_md_content = content

    def get_cached_claude_md_content(self) -> Optional[str]:
        return self.cached_claude_md_content

    # ============================================================================
    # Error Log
    # ============================================================================

    def add_to_in_memory_error_log(self, error_info: Dict[str, str]):
        if len(self.in_memory_error_log) >= MAX_IN_MEMORY_ERRORS:
            self.in_memory_error_log.pop(0)
        self.in_memory_error_log.append(error_info)

    def get_in_memory_error_log(self) -> List[Dict[str, str]]:
        return self.in_memory_error_log

    # ============================================================================
    # Setting Sources
    # ============================================================================

    def get_allowed_setting_sources(self) -> List[str]:
        return self.allowed_setting_sources

    def set_allowed_setting_sources(self, sources: List[str]):
        self.allowed_setting_sources = sources

    # ============================================================================
    # Plugins
    # ============================================================================

    def set_inline_plugins(self, plugins: List[str]):
        self.inline_plugins = plugins

    def get_inline_plugins(self) -> List[str]:
        return self.inline_plugins

    def set_chrome_flag_override(self, value: Optional[bool]):
        self.chrome_flag_override = value

    def get_chrome_flag_override(self) -> Optional[bool]:
        return self.chrome_flag_override

    def set_use_cowork_plugins(self, value: bool):
        self.use_cowork_plugins = value

    def get_use_cowork_plugins(self) -> bool:
        return self.use_cowork_plugins

    # ============================================================================
    # Permission Bypass
    # ============================================================================

    def set_session_bypass_permissions_mode(self, enabled: bool):
        self.session_bypass_permissions_mode = enabled

    def get_session_bypass_permissions_mode(self) -> bool:
        return self.session_bypass_permissions_mode

    # ============================================================================
    # Scheduled Tasks
    # ============================================================================

    def set_scheduled_tasks_enabled(self, enabled: bool):
        self.scheduled_tasks_enabled = enabled

    def get_scheduled_tasks_enabled(self) -> bool:
        return self.scheduled_tasks_enabled

    def get_session_cron_tasks(self) -> List[SessionCronTask]:
        return self.session_cron_tasks

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

    # ============================================================================
    # Session Trust / Persistence
    # ============================================================================

    def set_session_trust_accepted(self, accepted: bool):
        self.session_trust_accepted = accepted

    def get_session_trust_accepted(self) -> bool:
        return self.session_trust_accepted

    def set_session_persistence_disabled(self, disabled: bool):
        self.session_persistence_disabled = disabled

    def is_session_persistence_disabled(self) -> bool:
        return self.session_persistence_disabled

    # ============================================================================
    # Plan Mode
    # ============================================================================

    def has_exited_plan_mode_in_session(self) -> bool:
        return self.has_exited_plan_mode

    def set_has_exited_plan_mode(self, value: bool):
        self.has_exited_plan_mode = value

    def needs_plan_mode_exit_attachment_flag(self) -> bool:
        return self.needs_plan_mode_exit_attachment

    def set_needs_plan_mode_exit_attachment(self, value: bool):
        self.needs_plan_mode_exit_attachment = value

    def handle_plan_mode_transition(self, from_mode: str, to_mode: str):
        if to_mode == "plan" and from_mode != "plan":
            self.needs_plan_mode_exit_attachment = False
        if from_mode == "plan" and to_mode != "plan":
            self.needs_plan_mode_exit_attachment = True

    def needs_auto_mode_exit_attachment_flag(self) -> bool:
        return self.needs_auto_mode_exit_attachment

    def set_needs_auto_mode_exit_attachment(self, value: bool):
        self.needs_auto_mode_exit_attachment = value

    def handle_auto_mode_transition(self, from_mode: str, to_mode: str):
        if (from_mode == "auto" and to_mode == "plan") or (from_mode == "plan" and to_mode == "auto"):
            return
        from_is_auto = from_mode == "auto"
        to_is_auto = to_mode == "auto"
        if to_is_auto and not from_is_auto:
            self.needs_auto_mode_exit_attachment = False
        if from_is_auto and not to_is_auto:
            self.needs_auto_mode_exit_attachment = True

    # ============================================================================
    # LSP Recommendation
    # ============================================================================

    def has_shown_lsp_recommendation_this_session(self) -> bool:
        return self.lsp_recommendation_shown_this_session

    def set_lsp_recommendation_shown_this_session(self, value: bool):
        self.lsp_recommendation_shown_this_session = value

    # ============================================================================
    # SDK Init / Hooks
    # ============================================================================

    def set_init_json_schema(self, schema: Dict[str, Any]):
        self.init_json_schema = schema

    def get_init_json_schema(self) -> Optional[Dict[str, Any]]:
        return self.init_json_schema

    def register_hook_callbacks(self, hooks: Dict[str, List[Any]]):
        if self.registered_hooks is None:
            self.registered_hooks = {}
        for event, matchers in hooks.items():
            if event not in self.registered_hooks:
                self.registered_hooks[event] = []
            self.registered_hooks[event].extend(matchers)

    def get_registered_hooks(self) -> Optional[Dict[str, List[Any]]]:
        return self.registered_hooks

    def clear_registered_hooks(self):
        self.registered_hooks = None

    # ============================================================================
    # Plan Slug Cache / Teams
    # ============================================================================

    def get_plan_slug_cache(self) -> Dict[str, str]:
        return self.plan_slug_cache

    def get_session_created_teams(self) -> Set[str]:
        return self.session_created_teams

    # ============================================================================
    # Teleported Session
    # ============================================================================

    def set_teleported_session_info(self, info: Dict[str, Optional[str]]):
        self.teleported_session_info = TeleportedSessionInfo(
            is_teleported=True,
            has_logged_first_message=False,
            session_id=info.get("sessionId"),
        )

    def get_teleported_session_info(self) -> Optional[TeleportedSessionInfo]:
        return self.teleported_session_info

    def mark_first_teleport_message_logged(self):
        if self.teleported_session_info:
            self.teleported_session_info.has_logged_first_message = True

    # ============================================================================
    # Invoked Skills
    # ============================================================================

    def add_invoked_skill(self, skill_name: str, skill_path: str, content: str, agent_id: Optional[str] = None):
        key = f"{agent_id or ''}:{skill_name}"
        self.invoked_skills[key] = InvokedSkillInfo(
            skill_name=skill_name,
            skill_path=skill_path,
            content=content,
            invoked_at=int(time.time() * 1000),
            agent_id=agent_id,
        )

    def get_invoked_skills(self) -> Dict[str, InvokedSkillInfo]:
        return self.invoked_skills

    def get_invoked_skills_for_agent(self, agent_id: Optional[str]) -> Dict[str, InvokedSkillInfo]:
        normalized_id = agent_id
        result: Dict[str, InvokedSkillInfo] = {}
        for key, skill in self.invoked_skills.items():
            if skill.agent_id == normalized_id:
                result[key] = skill
        return result

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

    def clear_invoked_skills_for_agent(self, agent_id: str):
        keys_to_delete = [k for k, s in self.invoked_skills.items() if s.agent_id == agent_id]
        for key in keys_to_delete:
            del self.invoked_skills[key]

    # ============================================================================
    # Slow Operations
    # ============================================================================

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

    def get_slow_operations(self) -> List[SlowOperation]:
        now = int(time.time() * 1000)
        if any(op for op in self.slow_operations if now - op.timestamp >= SLOW_OPERATION_TTL_MS):
            self.slow_operations = [
                op for op in self.slow_operations if now - op.timestamp < SLOW_OPERATION_TTL_MS
            ]
            if not self.slow_operations:
                return []
        return self.slow_operations

    # ============================================================================
    # Main Thread Agent / Remote Mode
    # ============================================================================

    def get_main_thread_agent_type(self) -> Optional[str]:
        return self.main_thread_agent_type

    def set_main_thread_agent_type(self, agent_type: Optional[str]):
        self.main_thread_agent_type = agent_type

    def get_is_remote_mode(self) -> bool:
        return self.is_remote_mode

    def set_is_remote_mode(self, value: bool):
        self.is_remote_mode = value

    # ============================================================================
    # System Prompt Section Cache
    # ============================================================================

    def get_system_prompt_section_cache(self) -> Dict[str, Optional[str]]:
        return self.system_prompt_section_cache

    def set_system_prompt_section_cache_entry(self, name: str, value: Optional[str]):
        self.system_prompt_section_cache[name] = value

    def clear_system_prompt_section_state(self):
        self.system_prompt_section_cache.clear()

    # ============================================================================
    # Last Emitted Date
    # ============================================================================

    def get_last_emitted_date(self) -> Optional[str]:
        return self.last_emitted_date

    def set_last_emitted_date(self, date: Optional[str]):
        self.last_emitted_date = date

    # ============================================================================
    # Additional Directories / Channels
    # ============================================================================

    def get_additional_directories_for_claude_md(self) -> List[str]:
        return self.additional_directories_for_claude_md

    def set_additional_directories_for_claude_md(self, directories: List[str]):
        self.additional_directories_for_claude_md = directories

    def get_allowed_channels(self) -> List[ChannelEntry]:
        return self.allowed_channels

    def set_allowed_channels(self, entries: List[ChannelEntry]):
        self.allowed_channels = entries

    def get_has_dev_channels(self) -> bool:
        return self.has_dev_channels

    def set_has_dev_channels(self, value: bool):
        self.has_dev_channels = value

    # ============================================================================
    # Prompt Cache / Beta Latches
    # ============================================================================

    def get_prompt_cache_1h_allowlist(self) -> Optional[List[str]]:
        return self.prompt_cache_1h_allowlist

    def set_prompt_cache_1h_allowlist(self, allowlist: Optional[List[str]]):
        self.prompt_cache_1h_allowlist = allowlist

    def get_prompt_cache_1h_eligible(self) -> Optional[bool]:
        return self.prompt_cache_1h_eligible

    def set_prompt_cache_1h_eligible(self, eligible: Optional[bool]):
        self.prompt_cache_1h_eligible = eligible

    def get_afk_mode_header_latched(self) -> Optional[bool]:
        return self.afk_mode_header_latched

    def set_afk_mode_header_latched(self, v: bool):
        self.afk_mode_header_latched = v

    def get_fast_mode_header_latched(self) -> Optional[bool]:
        return self.fast_mode_header_latched

    def set_fast_mode_header_latched(self, v: bool):
        self.fast_mode_header_latched = v

    def get_cache_editing_header_latched(self) -> Optional[bool]:
        return self.cache_editing_header_latched

    def set_cache_editing_header_latched(self, v: bool):
        self.cache_editing_header_latched = v

    def get_thinking_clear_latched(self) -> Optional[bool]:
        return self.thinking_clear_latched

    def set_thinking_clear_latched(self, v: bool):
        self.thinking_clear_latched = v

    def clear_beta_header_latches(self):
        self.afk_mode_header_latched = None
        self.fast_mode_header_latched = None
        self.cache_editing_header_latched = None
        self.thinking_clear_latched = None

    # ============================================================================
    # Prompt ID
    # ============================================================================

    def get_prompt_id(self) -> Optional[str]:
        return self.prompt_id

    def set_prompt_id(self, id: Optional[str]):
        self.prompt_id = id
