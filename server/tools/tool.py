from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel

from server.models.tools import ToolInputJSONSchema, ToolResult, ValidationResult

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput")
TProgress = TypeVar("TProgress")


class ToolUseContext(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class ToolPermissionContext(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class AssistantMessage(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class PermissionResult(BaseModel):
    behavior: str = "allow"
    updated_input: Optional[Dict[str, Any]] = None
    message: str = ""


class ToolResultBlockParam(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class Tool(
    ABC,
    Generic[TInput, TOutput, TProgress],
):
    """
    Abstract base class for all tools. Every field is extracted from
    src/Tool.ts Tool<Input, Output, P> type (lines 362-695).

    Type parameters:
      TInput  - Pydantic BaseModel for input schema
      TOutput - Tool result output type
      TProgress - Tool progress data type
    """

    # ---------- required fields ----------

    @property
    @abstractmethod
    def name(self) -> str:
        """Primary tool name. Readonly."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> type[TInput]:
        """Pydantic model class for input validation."""
        ...

    @property
    @abstractmethod
    def max_result_size_chars(self) -> int:
        """Maximum result size in characters before persistence. Set to infinity for tools whose output must never be persisted."""
        ...

    @abstractmethod
    async def call(
        self,
        args: TInput,
        context: Any,
        can_use_tool: Any,
        parent_message: Any,
        on_progress: Any = None,
    ) -> ToolResult:
        ...

    @abstractmethod
    async def description(self, input: TInput, options: Dict[str, Any]) -> str:
        ...

    @abstractmethod
    async def prompt(self, options: Dict[str, Any]) -> str:
        ...

    @abstractmethod
    def user_facing_name(self, input: Optional[Dict[str, Any]] = None) -> str:
        ...

    @abstractmethod
    def to_auto_classifier_input(self, input: TInput) -> Any:
        ...

    @abstractmethod
    def map_tool_result_to_tool_result_block_param(
        self, content: TOutput, tool_use_id: str
    ) -> Any:
        ...

    @abstractmethod
    def render_tool_use_message(self, input: Dict[str, Any], options: Dict[str, Any]) -> Any:
        ...

    # ---------- optional fields ----------

    @property
    def aliases(self) -> Optional[List[str]]:
        """Optional aliases for backwards compatibility when a tool is renamed."""
        return None

    @property
    def search_hint(self) -> Optional[str]:
        """One-line capability phrase used by ToolSearch for keyword matching. 3-10 words, no trailing period."""
        return None

    @property
    def input_json_schema(self) -> Optional[ToolInputJSONSchema]:
        """Input schema directly in JSON Schema format (for MCP tools)."""
        return None

    @property
    def output_schema(self) -> Optional[Any]:
        """Output Zod schema (optional, some tools don't define this)."""
        return None

    def inputs_equivalent(self, a: TInput, b: TInput) -> bool:
        """Check if two inputs are equivalent. Used for dedup."""
        return False

    def is_concurrency_safe(self, input: TInput) -> bool:
        """Returns False by default (assume not safe). Source: TOOL_DEFAULTS."""
        return False

    def is_enabled(self) -> bool:
        """Returns True by default. Source: TOOL_DEFAULTS."""
        return True

    def is_read_only(self, input: TInput) -> bool:
        """Returns False by default (assume writes). Source: TOOL_DEFAULTS."""
        return False

    def is_destructive(self, input: TInput) -> bool:
        """Returns False by default. Source: TOOL_DEFAULTS."""
        return False

    def interrupt_behavior(self) -> str:
        """Returns 'block' by default (keep running when interrupted). 'cancel' means stop the tool."""
        return "block"

    def is_search_or_read_command(self, input: TInput) -> Optional[Dict[str, bool]]:
        """Returns info about whether tool use is search/read/list operation."""
        return None

    def is_open_world(self, input: TInput) -> bool:
        """Whether this tool use interacts with the outside world."""
        return True

    def requires_user_interaction(self) -> bool:
        """Whether the tool requires interactive user input."""
        return False

    @property
    def is_mcp(self) -> bool:
        """Whether this is an MCP tool."""
        return False

    @property
    def is_lsp(self) -> bool:
        """Whether this is an LSP tool."""
        return False

    @property
    def should_defer(self) -> bool:
        """When True, tool is deferred and requires ToolSearch before it can be called."""
        return False

    @property
    def always_load(self) -> bool:
        """When True, tool is never deferred - full schema always in initial prompt."""
        return False

    @property
    def mcp_info(self) -> Optional[Dict[str, str]]:
        """MCP server/tool names as received from the MCP server."""
        return None

    @property
    def strict(self) -> bool:
        """When True, enables strict mode for this tool in the API call."""
        return False

    def backfill_observable_input(self, input: Dict[str, Any]) -> None:
        """Called on copies of tool_use input before observers see it. Mutate in place. Must be idempotent."""
        pass

    async def validate_input(self, input: TInput, context: Any) -> ValidationResult:
        """Determines if this tool is allowed to run with this input."""
        return ValidationResult(valid=True)

    async def check_permissions(self, input: Dict[str, Any], context: Any) -> PermissionResult:
        """Determines if the user is asked for permission. Default: allow. Source: TOOL_DEFAULTS."""
        return PermissionResult(behavior="allow", updated_input=input)

    def get_path(self, input: TInput) -> Optional[str]:
        """Optional method for tools that operate on a file path."""
        return None

    async def prepare_permission_matcher(
        self, input: TInput
    ) -> Optional[Any]:
        """Prepare a matcher for hook 'if' conditions. Returns a callable."""
        return None

    def user_facing_name_background_color(
        self, input: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Returns a theme color key for the user-facing name background."""
        return None

    def is_transparent_wrapper(self) -> bool:
        """Transparent wrappers delegate rendering to their progress handler."""
        return False

    def get_tool_use_summary(
        self, input: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Short string summary of this tool use for display in compact views."""
        return None

    def get_activity_description(
        self, input: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Human-readable present-tense activity description for spinner display."""
        return None

    def render_tool_result_message(
        self,
        content: TOutput,
        progress_messages_for_message: List[Any],
        options: Dict[str, Any],
    ) -> Any:
        """Render the tool result. Optional - when omitted, result renders nothing."""
        return None

    def extract_search_text(self, out: TOutput) -> Optional[str]:
        """Flattened text of renderToolResultMessage IN TRANSCRIPT MODE."""
        return None

    def is_result_truncated(self, output: TOutput) -> bool:
        """Returns True when non-verbose rendering of this output is truncated."""
        return False

    def render_tool_use_tag(self, input: Dict[str, Any]) -> Any:
        """Renders optional tag to display after the tool use message."""
        return None

    def render_tool_use_progress_message(
        self,
        progress_messages_for_message: List[Any],
        options: Dict[str, Any],
    ) -> Any:
        """Render progress UI while the tool runs."""
        return None

    def render_tool_use_queued_message(self) -> Any:
        """Render queued UI before execution starts."""
        return None

    def render_tool_use_rejected_message(
        self, input: TInput, options: Dict[str, Any]
    ) -> Any:
        """Custom rejection UI. Falls back to FallbackToolUseRejectedMessage."""
        return None

    def render_tool_use_error_message(
        self, result: Any, options: Dict[str, Any]
    ) -> Any:
        """Custom error UI. Falls back to FallbackToolUseErrorMessage."""
        return None

    def render_grouped_tool_use(
        self,
        tool_uses: List[Dict[str, Any]],
        options: Dict[str, Any],
    ) -> Any:
        """Renders multiple tool uses as a group (non-verbose mode only)."""
        return None


Tools = List[Tool]


def tool_matches_name(tool: Tool, name: str) -> bool:
    """Checks if a tool matches the given name (primary name or alias). Source: Tool.ts L348-353."""
    if tool.name == name:
        return True
    aliases = tool.aliases
    if aliases is not None and name in aliases:
        return True
    return False


def find_tool_by_name(tools: Tools, name: str) -> Optional[Tool]:
    """Finds a tool by name or alias from a list of tools. Source: Tool.ts L358-360."""
    for t in tools:
        if tool_matches_name(t, name):
            return t
    return None


# ---------------------------------------------------------------------------
# buildTool – fills defaults for the 7 defaultable keys
# ---------------------------------------------------------------------------

TOOL_DEFAULTS = {
    "is_enabled": 1,
    "is_concurrency_safe": 1,
    "is_read_only": 1,
    "is_destructive": 1,
    "check_permissions": 1,
    "to_auto_classifier_input": 1,
    "user_facing_name": 1,
}
"""Keys that buildTool supplies defaults for. Source: Tool.ts L707-714."""


class ToolDef:
    """
    Tool definition that buildTool fills defaults into.
    Mirrors ToolDef<Input, Output, P> from Tool.ts L721-726.

    Any of the defaultable keys may be omitted; buildTool fills them in.
    """

    def __init__(
        self,
        *,
        name: str,
        input_schema: type,
        call: Any,
        description: Any,
        prompt: Any,
        render_tool_use_message: Any,
        map_tool_result_to_tool_result_block_param: Any,
        max_result_size_chars: int = 30000,
        aliases: Optional[List[str]] = None,
        search_hint: Optional[str] = None,
        input_json_schema: Optional[ToolInputJSONSchema] = None,
        output_schema: Optional[Any] = None,
        inputs_equivalent: Any = None,
        is_concurrency_safe: Any = None,
        is_enabled: Any = None,
        is_read_only: Any = None,
        is_destructive: Any = None,
        interrupt_behavior: Any = None,
        is_search_or_read_command: Any = None,
        is_open_world: Any = None,
        requires_user_interaction: Any = None,
        is_mcp: bool = False,
        is_lsp: bool = False,
        should_defer: bool = False,
        always_load: bool = False,
        mcp_info: Optional[Dict[str, str]] = None,
        strict: bool = False,
        backfill_observable_input: Any = None,
        validate_input: Any = None,
        check_permissions: Any = None,
        get_path: Any = None,
        prepare_permission_matcher: Any = None,
        user_facing_name: Any = None,
        user_facing_name_background_color: Any = None,
        is_transparent_wrapper: Any = None,
        get_tool_use_summary: Any = None,
        get_activity_description: Any = None,
        to_auto_classifier_input: Any = None,
        render_tool_result_message: Any = None,
        extract_search_text: Any = None,
        is_result_truncated: Any = None,
        render_tool_use_tag: Any = None,
        render_tool_use_progress_message: Any = None,
        render_tool_use_queued_message: Any = None,
        render_tool_use_rejected_message: Any = None,
        render_tool_use_error_message: Any = None,
        render_grouped_tool_use: Any = None,
    ):
        self.def_name = name
        self.def_input_schema = input_schema
        self.def_call = call
        self.def_description = description
        self.def_prompt = prompt
        self.def_render_tool_use_message = render_tool_use_message
        self.def_map_tool_result_to_tool_result_block_param = map_tool_result_to_tool_result_block_param
        self.def_max_result_size_chars = max_result_size_chars
        self.def_aliases = aliases
        self.def_search_hint = search_hint
        self.def_input_json_schema = input_json_schema
        self.def_output_schema = output_schema
        self.def_inputs_equivalent = inputs_equivalent
        self.def_is_concurrency_safe = is_concurrency_safe
        self.def_is_enabled = is_enabled
        self.def_is_read_only = is_read_only
        self.def_is_destructive = is_destructive
        self.def_interrupt_behavior = interrupt_behavior
        self.def_is_search_or_read_command = is_search_or_read_command
        self.def_is_open_world = is_open_world
        self.def_requires_user_interaction = requires_user_interaction
        self.def_is_mcp = is_mcp
        self.def_is_lsp = is_lsp
        self.def_should_defer = should_defer
        self.def_always_load = always_load
        self.def_mcp_info = mcp_info
        self.def_strict = strict
        self.def_backfill_observable_input = backfill_observable_input
        self.def_validate_input = validate_input
        self.def_check_permissions = check_permissions
        self.def_get_path = get_path
        self.def_prepare_permission_matcher = prepare_permission_matcher
        self.def_user_facing_name = user_facing_name
        self.def_user_facing_name_background_color = user_facing_name_background_color
        self.def_is_transparent_wrapper = is_transparent_wrapper
        self.def_get_tool_use_summary = get_tool_use_summary
        self.def_get_activity_description = get_activity_description
        self.def_to_auto_classifier_input = to_auto_classifier_input
        self.def_render_tool_result_message = render_tool_result_message
        self.def_extract_search_text = extract_search_text
        self.def_is_result_truncated = is_result_truncated
        self.def_render_tool_use_tag = render_tool_use_tag
        self.def_render_tool_use_progress_message = render_tool_use_progress_message
        self.def_render_tool_use_queued_message = render_tool_use_queued_message
        self.def_render_tool_use_rejected_message = render_tool_use_rejected_message
        self.def_render_tool_use_error_message = render_tool_use_error_message
        self.def_render_grouped_tool_use = render_grouped_tool_use


def build_tool(def_: ToolDef) -> Tool:
    """
    Build a complete Tool from a ToolDef, filling in safe defaults.
    Source: Tool.ts L783-792 (buildTool function).

    Defaults (fail-closed where it matters):
      - is_enabled → True
      - is_concurrency_safe → False (assume not safe)
      - is_read_only → False (assume writes)
      - is_destructive → False
      - check_permissions → { behavior: 'allow', updatedInput: input }
      - to_auto_classifier_input → ''
      - user_facing_name → tool name
    """

    class BuiltTool(Tool):
        @property
        def name(self) -> str:
            return def_.def_name

        @property
        def aliases(self) -> Optional[List[str]]:
            return def_.def_aliases

        @property
        def search_hint(self) -> Optional[str]:
            return def_.def_search_hint

        @property
        def input_schema(self) -> type:
            return def_.def_input_schema

        @property
        def input_json_schema(self) -> Optional[ToolInputJSONSchema]:
            return def_.def_input_json_schema

        @property
        def output_schema(self) -> Optional[Any]:
            return def_.def_output_schema

        @property
        def max_result_size_chars(self) -> int:
            return def_.def_max_result_size_chars

        @property
        def is_mcp(self) -> bool:
            return def_.def_is_mcp

        @property
        def is_lsp(self) -> bool:
            return def_.def_is_lsp

        @property
        def should_defer(self) -> bool:
            return def_.def_should_defer

        @property
        def always_load(self) -> bool:
            return def_.def_always_load

        @property
        def mcp_info(self) -> Optional[Dict[str, str]]:
            return def_.def_mcp_info

        @property
        def strict(self) -> bool:
            return def_.def_strict

        async def call(self, args, context, can_use_tool, parent_message, on_progress=None):
            return await def_.def_call(args, context, can_use_tool, parent_message, on_progress)

        async def description(self, input, options):
            return await def_.def_description(input, options)

        async def prompt(self, options):
            return await def_.def_prompt(options)

        def user_facing_name(self, input=None):
            if def_.def_user_facing_name is not None:
                return def_.def_user_facing_name(input)
            return self.name

        def to_auto_classifier_input(self, input):
            if def_.def_to_auto_classifier_input is not None:
                return def_.def_to_auto_classifier_input(input)
            return ""

        def map_tool_result_to_tool_result_block_param(self, content, tool_use_id):
            return def_.def_map_tool_result_to_tool_result_block_param(content, tool_use_id)

        def render_tool_use_message(self, input, options):
            return def_.def_render_tool_use_message(input, options)

        def inputs_equivalent(self, a, b):
            if def_.def_inputs_equivalent is not None:
                return def_.def_inputs_equivalent(a, b)
            return False

        def is_concurrency_safe(self, input):
            if def_.def_is_concurrency_safe is not None:
                return def_.def_is_concurrency_safe(input)
            return False

        def is_enabled(self):
            if def_.def_is_enabled is not None:
                return def_.def_is_enabled()
            return True

        def is_read_only(self, input):
            if def_.def_is_read_only is not None:
                return def_.def_is_read_only(input)
            return False

        def is_destructive(self, input):
            if def_.def_is_destructive is not None:
                return def_.def_is_destructive(input)
            return False

        def interrupt_behavior(self):
            if def_.def_interrupt_behavior is not None:
                return def_.def_interrupt_behavior()
            return "block"

        def is_search_or_read_command(self, input):
            if def_.def_is_search_or_read_command is not None:
                return def_.def_is_search_or_read_command(input)
            return None

        def is_open_world(self, input):
            if def_.def_is_open_world is not None:
                return def_.def_is_open_world(input)
            return True

        def requires_user_interaction(self):
            if def_.def_requires_user_interaction is not None:
                return def_.def_requires_user_interaction()
            return False

        async def validate_input(self, input, context):
            if def_.def_validate_input is not None:
                return await def_.def_validate_input(input, context)
            return ValidationResult(valid=True)

        async def check_permissions(self, input, context=None):
            if def_.def_check_permissions is not None:
                return await def_.def_check_permissions(input, context)
            return PermissionResult(behavior="allow", updated_input=input)

        def get_path(self, input):
            if def_.def_get_path is not None:
                return def_.def_get_path(input)
            return None

        async def prepare_permission_matcher(self, input):
            if def_.def_prepare_permission_matcher is not None:
                return await def_.def_prepare_permission_matcher(input)
            return None

        def user_facing_name_background_color(self, input=None):
            if def_.def_user_facing_name_background_color is not None:
                return def_.def_user_facing_name_background_color(input)
            return None

        def is_transparent_wrapper(self):
            if def_.def_is_transparent_wrapper is not None:
                return def_.def_is_transparent_wrapper()
            return False

        def get_tool_use_summary(self, input=None):
            if def_.def_get_tool_use_summary is not None:
                return def_.def_get_tool_use_summary(input)
            return None

        def get_activity_description(self, input=None):
            if def_.def_get_activity_description is not None:
                return def_.def_get_activity_description(input)
            return None

        def render_tool_result_message(self, content, progress_messages_for_message, options):
            if def_.def_render_tool_result_message is not None:
                return def_.def_render_tool_result_message(content, progress_messages_for_message, options)
            return None

        def extract_search_text(self, out):
            if def_.def_extract_search_text is not None:
                return def_.def_extract_search_text(out)
            return None

        def is_result_truncated(self, output):
            if def_.def_is_result_truncated is not None:
                return def_.def_is_result_truncated(output)
            return False

        def render_tool_use_tag(self, input):
            if def_.def_render_tool_use_tag is not None:
                return def_.def_render_tool_use_tag(input)
            return None

        def render_tool_use_progress_message(self, progress_messages_for_message, options):
            if def_.def_render_tool_use_progress_message is not None:
                return def_.def_render_tool_use_progress_message(progress_messages_for_message, options)
            return None

        def render_tool_use_queued_message(self):
            if def_.def_render_tool_use_queued_message is not None:
                return def_.def_render_tool_use_queued_message()
            return None

        def render_tool_use_rejected_message(self, input, options):
            if def_.def_render_tool_use_rejected_message is not None:
                return def_.def_render_tool_use_rejected_message(input, options)
            return None

        def render_tool_use_error_message(self, result, options):
            if def_.def_render_tool_use_error_message is not None:
                return def_.def_render_tool_use_error_message(result, options)
            return None

        def render_grouped_tool_use(self, tool_uses, options):
            if def_.def_render_grouped_tool_use is not None:
                return def_.def_render_grouped_tool_use(tool_uses, options)
            return None

        def backfill_observable_input(self, input):
            if def_.def_backfill_observable_input is not None:
                def_.def_backfill_observable_input(input)

    return BuiltTool()
