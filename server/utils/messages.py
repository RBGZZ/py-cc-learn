from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union

INTERRUPT_MESSAGE = "[Request interrupted by user]"
INTERRUPT_MESSAGE_FOR_TOOL_USE = "[Request interrupted by user for tool use]"
CANCEL_MESSAGE = (
    "The user doesn't want to take this action right now. "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "STOP what you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "The user doesn't want to proceed with this tool use. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "To tell you how to proceed, the user said:\n"
)
SUBAGENT_REJECT_MESSAGE = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "Try a different approach or report the limitation to complete your task."
)
SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "Permission for this tool use was denied. "
    "The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). "
    "The user said:\n"
)
NO_RESPONSE_REQUESTED = "No response requested."
NO_CONTENT_MESSAGE = "[No content]"
SYNTHETIC_MODEL = "<synthetic>"
SYNTHETIC_TOOL_RESULT_PLACEHOLDER = "[Tool result missing due to internal error]"
TOOL_REFERENCE_TURN_BOUNDARY = "Tool loaded."

SYNTHETIC_MESSAGES: Set[str] = {
    INTERRUPT_MESSAGE,
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    CANCEL_MESSAGE,
    REJECT_MESSAGE,
    NO_RESPONSE_REQUESTED,
}

DENIAL_WORKAROUND_GUIDANCE = (
    "IMPORTANT: You *may* attempt to accomplish this action using other tools "
    "that might naturally be used to accomplish this goal, "
    "e.g. using head instead of cat. But you *should not* attempt to work around "
    "this denial in malicious ways, "
    "e.g. do not use your ability to run tests to execute non-test actions. "
    "You should only try to work around this restriction in reasonable ways "
    "that do not attempt to bypass the intent behind this denial. "
    "If you believe this capability is essential to complete the user's request, "
    "STOP and explain to the user what you were trying to do and why you need "
    "this permission. Let the user decide how to proceed."
)


def derive_short_message_id(uuid_str: str) -> str:
    hex_str = uuid_str.replace("-", "")
    first_hex = hex_str[:10]
    return _base36_encode(int(first_hex, 16))[:6]


def _base36_encode(num: int) -> str:
    if num == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = ""
    while num > 0:
        num, rem = divmod(num, 36)
        result = alphabet[rem] + result
    return result


def auto_reject_message(tool_name: str) -> str:
    return f"Permission to use {tool_name} has been denied. {DENIAL_WORKAROUND_GUIDANCE}"


def dont_ask_reject_message(tool_name: str) -> str:
    return (
        f"Permission to use {tool_name} has been denied because Claude Code is "
        f"running in don't ask mode. {DENIAL_WORKAROUND_GUIDANCE}"
    )


def is_synthetic_message(message: Dict[str, Any]) -> bool:
    msg_type = message.get("type", "")
    if msg_type in ("progress", "attachment", "system"):
        return False
    msg_content = message.get("message", {}).get("content", [])
    if isinstance(msg_content, list) and len(msg_content) > 0:
        first_block = msg_content[0]
        if (
            isinstance(first_block, dict)
            and first_block.get("type") == "text"
            and first_block.get("text", "") in SYNTHETIC_MESSAGES
        ):
            return True
    return False


def create_user_message(
    content: Union[str, List[Dict[str, Any]]],
    is_meta: bool = False,
    is_virtual: bool = False,
    is_compact_summary: bool = False,
    tool_use_result: Any = None,
    uuid_val: Optional[str] = None,
    timestamp: Optional[str] = None,
    permission_mode: Optional[str] = None,
    origin: Optional[str] = None,
) -> Dict[str, Any]:
    msg_uuid = uuid_val or str(_uuid.uuid4())
    msg = {
        "type": "user",
        "uuid": msg_uuid,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "message": {
            "role": "user",
            "content": content or NO_CONTENT_MESSAGE,
        },
        "isMeta": is_meta,
        "isVirtual": is_virtual,
        "isCompactSummary": is_compact_summary,
        "toolUseResult": tool_use_result,
        "permissionMode": permission_mode,
        "origin": origin,
    }
    return msg


def create_user_interruption_message(tool_use: bool = False) -> Dict[str, Any]:
    content = INTERRUPT_MESSAGE_FOR_TOOL_USE if tool_use else INTERRUPT_MESSAGE
    return create_user_message(content=[{"type": "text", "text": content}])


def create_assistant_message(
    content: Union[str, List[Dict[str, Any]]],
    model: str = SYNTHETIC_MODEL,
    usage: Optional[Dict[str, Any]] = None,
    is_virtual: bool = False,
) -> Dict[str, Any]:
    if isinstance(content, str):
        content_blocks: List[Dict[str, Any]] = [
            {
                "type": "text",
                "text": content if content else NO_CONTENT_MESSAGE,
            }
        ]
    else:
        content_blocks = content

    if usage is None:
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
            "service_tier": None,
            "cache_creation": {
                "ephemeral_1h_input_tokens": 0,
                "ephemeral_5m_input_tokens": 0,
            },
            "inference_geo": None,
            "iterations": None,
            "speed": None,
        }

    return {
        "type": "assistant",
        "uuid": str(_uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": {
            "id": str(_uuid.uuid4()),
            "container": None,
            "model": model,
            "role": "assistant",
            "stop_reason": "stop_sequence",
            "stop_sequence": "",
            "type": "message",
            "usage": usage,
            "content": content_blocks,
            "context_management": None,
        },
        "requestId": None,
        "apiError": None,
        "error": None,
        "errorDetails": None,
        "isApiErrorMessage": False,
        "isVirtual": is_virtual,
    }


def create_assistant_api_error_message(
    content: str,
    api_error: Any = None,
    error: Any = None,
    error_details: Optional[str] = None,
) -> Dict[str, Any]:
    msg = create_assistant_message(
        content=content if content else NO_CONTENT_MESSAGE,
        model=SYNTHETIC_MODEL,
    )
    msg["isApiErrorMessage"] = True
    msg["apiError"] = api_error
    msg["error"] = error
    msg["errorDetails"] = error_details
    return msg


def create_tool_result_stop_message(tool_use_id: str) -> Dict[str, Any]:
    return {
        "type": "tool_result",
        "content": CANCEL_MESSAGE,
        "is_error": True,
        "tool_use_id": tool_use_id,
    }


def create_progress_message(
    tool_use_id: str,
    parent_tool_use_id: str,
    data: Any,
) -> Dict[str, Any]:
    return {
        "type": "progress",
        "data": data,
        "toolUseID": tool_use_id,
        "parentToolUseID": parent_tool_use_id,
        "uuid": str(_uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_last_assistant_message(
    messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for msg in reversed(messages):
        if msg.get("type") == "assistant":
            return msg
    return None


def has_tool_calls_in_last_assistant_turn(
    messages: List[Dict[str, Any]],
) -> bool:
    for msg in reversed(messages):
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                return any(
                    isinstance(block, dict) and block.get("type") == "tool_use"
                    for block in content
                )
    return False


def is_classifier_denial(content: str) -> bool:
    return content.startswith("Permission for this action has been denied. Reason: ")


def prepare_user_content(
    input_string: str,
    preceding_input_blocks: Optional[List[Dict[str, Any]]] = None,
) -> Union[str, List[Dict[str, Any]]]:
    if not preceding_input_blocks:
        return input_string
    return [*preceding_input_blocks, {"text": input_string, "type": "text"}]


def normalize_content(content: Union[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content or NO_CONTENT_MESSAGE}]
    return content


def filter_real_messages(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [
        m
        for m in messages
        if m.get("type") not in ("progress", "attachment")
        and not is_synthetic_message(m)
    ]
