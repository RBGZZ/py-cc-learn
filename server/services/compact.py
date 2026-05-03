from __future__ import annotations

import json
import math
import os
from typing import Any

from server.utils import tokens as token_utils

# === Micro-Compact Constants ===

TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"

IMAGE_MAX_TOKEN_SIZE = 2000

COMPACTABLE_TOOL_NAMES = {
    "fileread",
    "read",
    "bash",
    "shell",
    "grep",
    "glob",
    "websearch",
    "webfetch",
    "fileedit",
    "edit",
    "filewrite",
    "write",
    "lstool",
    "task",
    "todowrite",
    "notebookread",
    "notebookedit",
}

# === Auto-Compact Constants ===

AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000

MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3

COMPACT_MAX_OUTPUT_TOKENS = 20_000

MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000

# === Post-Compact Constants ===

POST_COMPACT_MAX_FILES_TO_RESTORE = 5
POST_COMPACT_TOKEN_BUDGET = 50_000
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000
POST_COMPACT_MAX_TOKENS_PER_SKILL = 5_000

# === Compact Prompts ===

NO_TOOLS_PREAMBLE = (
    "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
    "- Do NOT use Read, Bash, Grep, Glob, Edit, Write, or ANY other tool.\n"
    "- You already have all the context you need in the conversation above.\n"
    "- Tool calls will be REJECTED and will waste your only turn — you will fail the task.\n"
    "- Your entire response must be plain text: an <analysis> block followed by a <summary> block.\n\n"
)

NO_TOOLS_TRAILER = (
    "\n\nREMINDER: Do NOT call any tools. Respond with plain text only — "
    "an <analysis> block followed by a <summary> block. "
    "Tool calls will be rejected and you will fail the task."
)

COMPACT_ANALYSIS_INSTRUCTION = (
    "Before providing your final summary, wrap your analysis in <analysis> tags to organize "
    "your thoughts and ensure you've covered all necessary points. In your analysis process:\n\n"
    "1. Chronologically analyze each message and section of the conversation. For each section "
    "thoroughly identify:\n"
    "   - The user's explicit requests and intents\n"
    "   - Your approach to addressing the user's requests\n"
    "   - Key decisions, technical concepts and code patterns\n"
    "   - Specific details like:\n"
    "     - file names\n"
    "     - full code snippets\n"
    "     - function signatures\n"
    "     - file edits\n"
    "   - Errors that you ran into and how you fixed them\n"
    "   - Pay special attention to specific user feedback that you received, especially if the "
    "user told you to do something differently.\n"
    "2. Double-check for technical accuracy and completeness, addressing each required element "
    "thoroughly."
)

BASE_COMPACT_PROMPT = (
    "Your task is to create a detailed summary of the conversation so far, paying close attention "
    "to the user's explicit requests and your previous actions.\n"
    "This summary should be thorough in capturing technical details, code patterns, and "
    "architectural decisions that would be essential for continuing development work without "
    "losing context.\n\n"
    f"{COMPACT_ANALYSIS_INSTRUCTION}\n\n"
    "Your summary should include the following sections:\n\n"
    "1. Primary Request and Intent: Capture all of the user's explicit requests and intents "
    "in detail\n"
    "2. Key Technical Concepts: List all important technical concepts, technologies, and "
    "frameworks discussed.\n"
    "3. Files and Code Sections: Enumerate specific files and code sections examined, "
    "modified, or created. Pay special attention to the most recent messages and include full "
    "code snippets where applicable and include a summary of why this file read or edit is "
    "important.\n"
    "4. Errors and fixes: List all errors that you ran into, and how you fixed them. Pay "
    "special attention to specific user feedback that you received, especially if the user "
    "told you to do something differently.\n"
    "5. Problem Solving: Document problems solved and any ongoing troubleshooting efforts.\n"
    "6. All user messages: List ALL user messages that are not tool results. These are "
    "critical for understanding the users' feedback and changing intent.\n"
    "7. Pending Tasks: Outline any pending tasks that you have explicitly been asked to work on.\n"
    "8. Current Work: Describe in detail precisely what was being worked on immediately "
    "before this summary request, paying special attention to the most recent messages from "
    "both user and assistant. Include file names and code snippets where applicable.\n"
    "9. Optional Next Step: List the next step that you will take that is related to the "
    "most recent work you were doing. IMPORTANT: ensure that this step is DIRECTLY in line "
    "with the user's most recent explicit requests, and the task you were working on "
    "immediately before this summary request. If your last task was concluded, then only list "
    "next steps if they are explicitly in line with the users request. Do not start on "
    "tangential requests or really old requests that were already completed without confirming "
    "with the user first.\n"
    "                       If there is a next step, include direct quotes from the most "
    "recent conversation showing exactly what task you were working on and where you left off. "
    "This should be verbatim to ensure there's no drift in task interpretation.\n"
)

ERROR_MESSAGE_NOT_ENOUGH_MESSAGES = "Not enough messages to compact."
ERROR_MESSAGE_PROMPT_TOO_LONG = (
    "Conversation too long. Press esc twice to go up a few messages and try again."
)
ERROR_MESSAGE_USER_ABORT = "API Error: Request was aborted."
ERROR_MESSAGE_INCOMPLETE_RESPONSE = (
    "Compaction interrupted \u00b7 This may be due to network issues — please try again."
)
MAX_PTL_RETRIES = 3
PTL_RETRY_MARKER = "[earlier conversation truncated for compaction retry]"


def rough_token_count(text: str, use_tiktoken: bool = True, model: str = "cl100k_base") -> int:
    if not text:
        return 0
    if use_tiktoken:
        try:
            return token_utils.count_tokens(text, model)
        except Exception:
            pass
    return math.ceil(len(text) / 4)


def rough_token_count_for_messages(messages: list[dict[str, Any]], use_tiktoken: bool = True, model: str = "cl100k_base") -> int:
    if use_tiktoken:
        try:
            return token_utils.count_tokens_for_messages(messages, model)
        except Exception:
            pass
    total = 0
    for msg in messages:
        if msg.get("type") not in ("user", "assistant"):
            continue
        content = msg.get("message", {}).get("content", msg.get("content", []))
        if isinstance(content, str):
            total += rough_token_count(content, use_tiktoken=False)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    total += rough_token_count(block.get("text", ""), use_tiktoken=False)
                elif block_type == "tool_result":
                    total += _calculate_tool_result_tokens(block)
                elif block_type in ("image", "document"):
                    total += IMAGE_MAX_TOKEN_SIZE
                elif block_type == "thinking":
                    total += rough_token_count(block.get("thinking", ""), use_tiktoken=False)
                elif block_type == "redacted_thinking":
                    total += rough_token_count(block.get("data", ""), use_tiktoken=False)
                elif block_type == "tool_use":
                    total += rough_token_count(
                        block.get("name", "") + json.dumps(block.get("input", {})), use_tiktoken=False
                    )
                else:
                    total += rough_token_count(json.dumps(block), use_tiktoken=False)
    return math.ceil(total * (4 / 3))


def _calculate_tool_result_tokens(block: dict[str, Any], encoding=None) -> int:
    content = block.get("content")
    if not content:
        return 0
    if isinstance(content, str):
        if encoding:
            return len(encoding.encode(content))
        return rough_token_count(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "text":
                text = item.get("text", "")
                total += len(encoding.encode(text)) if encoding else rough_token_count(text)
            elif item_type in ("image", "document"):
                total += IMAGE_MAX_TOKEN_SIZE
        return total
    return 0


def _is_compactable_tool(tool_name: str) -> bool:
    return tool_name.lower() in COMPACTABLE_TOOL_NAMES


def _collect_compactable_tool_ids(messages: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for message in messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and _is_compactable_tool(block.get("name", "")):
                ids.append(block.get("id", ""))
    return ids


# === Micro-Compact ===


def microcompact_messages(
    messages: list[dict[str, Any]],
    tool_use_context: dict[str, Any] | None = None,
    query_source: str | None = None,
) -> dict[str, Any]:
    compactable_ids = _collect_compactable_tool_ids(messages)
    compactable_set = set(compactable_ids)

    encoding = None
    try:
        model = (
            tool_use_context.get("options", {}).get("main_loop_model", "claude-sonnet-4-20250514")
            if tool_use_context
            else "claude-sonnet-4-20250514"
        )
        encoding = token_utils._get_encoding_for_model(model)
    except Exception:
        pass

    tokens_saved = 0
    result: list[dict[str, Any]] = []

    for message in messages:
        if message.get("type") != "user":
            result.append(message)
            continue

        content = message.get("message", {}).get("content", [])
        if not isinstance(content, list):
            result.append(message)
            continue

        touched = False
        new_content: list[dict[str, Any]] = []
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_result"
                and block.get("tool_use_id") in compactable_set
                and block.get("content") != TIME_BASED_MC_CLEARED_MESSAGE
            ):
                tokens_saved += _calculate_tool_result_tokens(block, encoding)
                touched = True
                new_block = {**block, "content": TIME_BASED_MC_CLEARED_MESSAGE}
                new_content.append(new_block)
            else:
                new_content.append(block)

        if not touched:
            result.append(message)
        else:
            new_msg = {**message}
            new_msg["message"] = {**message.get("message", {}), "content": new_content}
            result.append(new_msg)

    return {
        "messages": result,
        "tokens_saved": tokens_saved,
    }


# === Auto-Compact ===


def get_auto_compact_threshold(
    model: str,
    effective_context_window: int | None = None,
) -> int:
    if effective_context_window is None:
        effective_context_window = _get_effective_context_window(model)

    threshold = effective_context_window - AUTOCOMPACT_BUFFER_TOKENS

    env_pct = os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if env_pct:
        try:
            pct = float(env_pct)
            if 0 < pct <= 100:
                pct_threshold = math.floor(effective_context_window * (pct / 100))
                return min(pct_threshold, threshold)
        except ValueError:
            pass

    return threshold


def _get_effective_context_window(model: str) -> int:
    context_window = _get_context_window_for_model(model)

    env_window = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW")
    if env_window:
        try:
            parsed = int(env_window)
            if parsed > 0:
                context_window = min(context_window, parsed)
        except ValueError:
            pass

    reserved = min(MAX_OUTPUT_TOKENS_FOR_SUMMARY, COMPACT_MAX_OUTPUT_TOKENS)
    return context_window - reserved


def _get_context_window_for_model(model: str) -> int:
    model_lower = model.lower()
    if model_supports_1m(model):
        return 1_000_000
    if "claude-sonnet-4" in model_lower or "claude-opus-4" in model_lower:
        return 200_000
    if "claude-haiku-4" in model_lower:
        return 175_000
    if "claude-3-5" in model_lower:
        return 200_000
    if "claude-3" in model_lower:
        return 200_000
    if "gpt-4" in model_lower:
        return 128_000
    if "gpt-3.5" in model_lower:
        return 16_385
    if "gemini" in model_lower:
        return 1_000_000
    if "claude-opus-4-6" in model_lower:
        return 1_000_000
    if "claude-sonnet-4-5" in model_lower:
        return 1_000_000
    return 200_000


def has_1m_context(model: str) -> bool:
    if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").lower() in ("1", "true"):
        return False
    return "[1m]" in model


def model_supports_1m(model: str) -> bool:
    if os.environ.get("CLAUDE_CODE_DISABLE_1M_CONTEXT", "").lower() in ("1", "true"):
        return False
    model_lower = model.lower()
    return "claude-sonnet-4" in model_lower or "opus-4-6" in model_lower


def is_auto_compact_enabled() -> bool:
    if os.environ.get("DISABLE_COMPACT") in ("1", "true", "TRUE"):
        return False
    if os.environ.get("DISABLE_AUTO_COMPACT") in ("1", "true", "TRUE"):
        return False
    return True


def calculate_token_warning_state(
    token_usage: int,
    model: str,
) -> dict[str, Any]:
    auto_compact_threshold = get_auto_compact_threshold(model)
    effective_window = _get_effective_context_window(model)

    threshold = auto_compact_threshold if is_auto_compact_enabled() else effective_window

    percent_left = max(0, round(((threshold - token_usage) / threshold) * 100))

    warning_threshold = threshold - WARNING_THRESHOLD_BUFFER_TOKENS
    error_threshold = threshold - ERROR_THRESHOLD_BUFFER_TOKENS

    is_above_warning = token_usage >= warning_threshold
    is_above_error = token_usage >= error_threshold
    is_above_auto_compact = is_auto_compact_enabled() and token_usage >= auto_compact_threshold

    blocking_limit = effective_window - MANUAL_COMPACT_BUFFER_TOKENS
    env_override = os.environ.get("CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE")
    if env_override:
        try:
            parsed = int(env_override)
            if parsed > 0:
                blocking_limit = parsed
        except ValueError:
            pass

    is_at_blocking_limit = token_usage >= blocking_limit

    return {
        "percent_left": percent_left,
        "is_above_warning_threshold": is_above_warning,
        "is_above_error_threshold": is_above_error,
        "is_above_auto_compact_threshold": is_above_auto_compact,
        "is_at_blocking_limit": is_at_blocking_limit,
    }


async def should_auto_compact(
    messages: list[dict[str, Any]],
    model: str,
    query_source: str | None = None,
    snip_tokens_freed: int = 0,
) -> bool:
    if query_source in ("session_memory", "compact"):
        return False

    if not is_auto_compact_enabled():
        return False

    token_count = token_utils.token_count_with_estimation(messages, model) - snip_tokens_freed

    state = calculate_token_warning_state(token_count, model)
    return state["is_above_auto_compact_threshold"]


async def auto_compact_if_needed(
    messages: list[dict[str, Any]],
    tool_use_context: dict[str, Any],
    cache_safe_params: dict[str, Any] | None = None,
    query_source: str | None = None,
    tracking: dict[str, Any] | None = None,
    snip_tokens_freed: int = 0,
) -> dict[str, Any]:
    if os.environ.get("DISABLE_COMPACT") in ("1", "true", "TRUE"):
        return {"was_compacted": False}

    if tracking and tracking.get("consecutive_failures", 0) >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
        return {"was_compacted": False}

    model = tool_use_context.get("options", {}).get("main_loop_model", "claude-sonnet-4-20250514")

    should_compact = await should_auto_compact(messages, model, query_source, snip_tokens_freed)

    if not should_compact:
        return {"was_compacted": False}

    try:
        compact_prompt = get_compact_prompt()
        summary_request = {
            "type": "user",
            "message": {"role": "user", "content": compact_prompt},
        }

        summary = await _stream_compact_summary(messages, summary_request, tool_use_context, model)

        if not summary:
            raise Exception("Failed to generate conversation summary")

        formatted_summary = format_compact_summary(summary)

        boundary_marker = {
            "type": "system",
            "subtype": "compact_boundary",
            "compact_metadata": {
                "trigger": "auto",
                "pre_compact_token_count": token_utils.token_count_with_estimation(messages, model),
                "post_compact_summary_tokens": rough_token_count(formatted_summary) if formatted_summary else 0,
            },
        }

        compact_result = {
            "boundary_marker": boundary_marker,
            "summary": formatted_summary,
            "was_compacted": True,
            "consecutive_failures": 0,
        }

        return compact_result
    except Exception:
        prev_failures = tracking.get("consecutive_failures", 0) if tracking else 0
        next_failures = prev_failures + 1
        return {"was_compacted": False, "consecutive_failures": next_failures}


async def reactive_compact(
    messages: list[dict[str, Any]],
    tool_use_context: dict[str, Any],
) -> dict[str, Any]:
    """Re-compact after a compact failure. Uses the same prompt but with reactive flag."""
    import os
    if os.environ.get("DISABLE_COMPACT", "").lower() in ("1", "true"):
        return {"was_compacted": False}

    compact_prompt = get_compact_prompt()
    summary_request = {
        "type": "user",
        "message": {"role": "user", "content": compact_prompt},
    }

    model = tool_use_context.get("options", {}).get(
        "main_loop_model", "claude-sonnet-4-20250514"
    )
    summary = await _stream_compact_summary(messages, summary_request, tool_use_context, model)

    if not summary:
        return {"was_compacted": False}

    formatted_summary = format_compact_summary(summary)
    boundary_marker = {
        "type": "system",
        "subtype": "compact_boundary",
        "compact_metadata": {
            "trigger": "reactive",
        },
    }
    return {
        "boundary_marker": boundary_marker,
        "summary": formatted_summary,
        "was_compacted": True,
    }


async def context_collapse(
    messages: list[dict[str, Any]],
    tool_use_context: dict[str, Any],
) -> dict[str, Any]:
    """Collapse context when enabled via CLAUDE_CODE_CONTEXT_COLLAPSE env var."""
    import os
    if os.environ.get("CLAUDE_CODE_CONTEXT_COLLAPSE", "").lower() not in ("1", "true"):
        return {"was_compacted": False}
    return await reactive_compact(messages, tool_use_context)


# === Post-Compact Recovery ===


def create_post_compact_file_attachments(
    read_file_state: dict[str, dict[str, Any]],
    max_files: int = POST_COMPACT_MAX_FILES_TO_RESTORE,
    token_budget: int = POST_COMPACT_TOKEN_BUDGET,
    preserved_messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    preserved_paths = _collect_read_file_paths(preserved_messages or [])

    recent_files = sorted(
        [{"filename": f, **s} for f, s in read_file_state.items() if f not in preserved_paths],
        key=lambda x: x.get("timestamp", 0),
        reverse=True,
    )[:max_files]

    used_tokens = 0
    attachments: list[dict[str, Any]] = []

    for file_info in recent_files:
        content = file_info.get("content", "")
        file_tokens = rough_token_count(content)

        tokens_for_attachment = min(file_tokens, POST_COMPACT_MAX_TOKENS_PER_FILE)

        if used_tokens + tokens_for_attachment <= token_budget:
            attachments.append(
                {
                    "type": "attachment",
                    "attachment": {
                        "type": "file_reference",
                        "filename": file_info["filename"],
                        "content": content[: POST_COMPACT_MAX_TOKENS_PER_FILE * 4],
                    },
                }
            )
            used_tokens += tokens_for_attachment
        else:
            break

    return attachments


def _collect_read_file_paths(messages: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for msg in messages:
        if msg.get("type") != "assistant":
            continue
        content = msg.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use" or block.get("name", "").lower() not in (
                "fileread",
                "read",
            ):
                continue
            input_data = block.get("input", {})
            if isinstance(input_data, dict) and "file_path" in input_data:
                paths.add(input_data["file_path"])
    return paths


# === Compact Prompt ===


def get_compact_prompt(custom_instructions: str | None = None) -> str:
    prompt = NO_TOOLS_PREAMBLE + BASE_COMPACT_PROMPT
    if custom_instructions and custom_instructions.strip():
        prompt += f"\n\nAdditional Instructions:\n{custom_instructions}"
    prompt += NO_TOOLS_TRAILER
    return prompt


def format_compact_summary(summary: str) -> str:
    import re

    formatted = summary

    formatted = re.sub(r"<analysis>[\s\S]*?</analysis>", "", formatted)

    summary_match = re.search(r"<summary>([\s\S]*?)</summary>", formatted)
    if summary_match:
        content = summary_match.group(1) or ""
        formatted = formatted.replace(summary_match.group(0), f"Summary:\n{content.strip()}")

    formatted = re.sub(r"\n\n+", "\n\n", formatted)
    return formatted.strip()


def get_compact_user_summary_message(
    summary: str,
    suppress_follow_up_questions: bool = False,
    transcript_path: str | None = None,
    recent_messages_preserved: bool = False,
) -> str:
    formatted = format_compact_summary(summary)

    base = (
        "This session is being continued from a previous conversation that ran out of context. "
        f"The summary below covers the earlier portion of the conversation.\n\n{formatted}"
    )

    if transcript_path:
        base += (
            f"\n\nIf you need specific details from before compaction (like exact code snippets, "
            f"error messages, or content you generated), read the full transcript at: "
            f"{transcript_path}"
        )

    if recent_messages_preserved:
        base += "\n\nRecent messages are preserved verbatim."

    if suppress_follow_up_questions:
        base += (
            "\nContinue the conversation from where it left off without asking the user any "
            "further questions. Resume directly — do not acknowledge the summary, do not recap "
            'what was happening, do not preface with "I\'ll continue" or similar. Pick up the '
            "last task as if the break never happened."
        )

    return base


# === Post-Compact Cleanup ===


def run_post_compact_cleanup(query_source: str | None = None) -> None:
    pass


# === Internal Helpers ===


async def _stream_compact_summary(
    messages: list[dict[str, Any]],
    summary_request: dict[str, Any],
    tool_use_context: dict[str, Any],
    model: str,
) -> str | None:
    provider = tool_use_context.get("_provider")
    if provider is None:
        return None

    if hasattr(provider, 'config'):
        provider.config.max_tokens = COMPACT_MAX_OUTPUT_TOKENS

    system_prompt = "You are a helpful AI assistant tasked with summarizing conversations."

    request_messages = list(messages) + [summary_request]

    try:
        async for event in provider.stream_chat(
            messages=request_messages,
            system_prompt=system_prompt,
            model=model,
        ):
            if event.get("type") == "assistant":
                content = event.get("message", {}).get("content", "")
                if isinstance(content, list):
                    text_parts = [
                        b.get("text", "")
                        for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    ]
                    return "\n".join(text_parts)
                return str(content) if content else None
    except Exception:
        return None

    return None
