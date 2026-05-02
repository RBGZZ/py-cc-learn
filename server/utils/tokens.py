from __future__ import annotations

import functools
from typing import Any, Dict, List, Optional

import tiktoken

from server.utils.messages import SYNTHETIC_MESSAGES, SYNTHETIC_MODEL


@functools.lru_cache(maxsize=8)
def _get_encoding(encoding_name: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding_name)


@functools.lru_cache(maxsize=8)
def _get_encoding_for_model(model_name: str) -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model_name)
    except KeyError:
        return _get_encoding("cl100k_base")


def count_tokens(text: str, model: str = "cl100k_base") -> int:
    encoding = _get_encoding_for_model(model)
    return len(encoding.encode(text))


def count_tokens_for_messages(
    messages: List[Dict[str, Any]], model: str = "cl100k_base"
) -> int:
    encoding = _get_encoding_for_model(model)
    total = 0
    for msg in messages:
        content = msg.get("message", {}).get("content", msg.get("content", ""))
        if isinstance(content, str):
            total += len(encoding.encode(content))
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text", "")
                    if text:
                        total += len(encoding.encode(text))
    return total


def get_token_usage(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if message.get("type") != "assistant":
        return None
    if "usage" not in message.get("message", {}):
        return None
    content = message["message"].get("content", [])
    if (
        isinstance(content, list)
        and len(content) > 0
        and content[0].get("type") == "text"
        and content[0].get("text", "") in SYNTHETIC_MESSAGES
    ):
        return None
    if message["message"].get("model") == SYNTHETIC_MODEL:
        return None
    return message["message"]["usage"]


def get_token_count_from_usage(usage: Dict[str, Any]) -> int:
    return (
        usage.get("input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("output_tokens", 0)
    )


def token_count_from_last_api_response(
    messages: List[Dict[str, Any]],
) -> int:
    for msg in reversed(messages):
        usage = get_token_usage(msg)
        if usage:
            return get_token_count_from_usage(usage)
    return 0


def final_context_tokens_from_last_response(
    messages: List[Dict[str, Any]],
) -> int:
    for msg in reversed(messages):
        usage = get_token_usage(msg)
        if usage:
            iterations = usage.get("iterations")
            if iterations and len(iterations) > 0:
                last_iter = iterations[-1]
                return last_iter.get("input_tokens", 0) + last_iter.get(
                    "output_tokens", 0
                )
            return usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
    return 0


def message_token_count_from_last_api_response(
    messages: List[Dict[str, Any]],
) -> int:
    for msg in reversed(messages):
        usage = get_token_usage(msg)
        if usage:
            return usage.get("output_tokens", 0)
    return 0


def get_current_usage(
    messages: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for msg in reversed(messages):
        usage = get_token_usage(msg)
        if usage:
            return {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_creation_input_tokens": usage.get(
                    "cache_creation_input_tokens", 0
                ),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            }
    return None


def does_most_recent_assistant_message_exceed_200k(
    messages: List[Dict[str, Any]],
) -> bool:
    THRESHOLD = 200_000
    for msg in reversed(messages):
        if msg.get("type") == "assistant":
            usage = get_token_usage(msg)
            if usage:
                return get_token_count_from_usage(usage) > THRESHOLD
            return False
    return False


def token_count_with_estimation(
    messages: List[Dict[str, Any]], model: str = "cl100k_base"
) -> int:
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        usage = get_token_usage(msg)
        if usage:
            response_id = msg.get("message", {}).get("id")
            if response_id:
                j = i - 1
                while j >= 0:
                    prior = messages[j]
                    prior_id = prior.get("message", {}).get("id") if prior else None
                    if prior_id == response_id:
                        i = j
                    elif prior_id is not None:
                        break
                    j -= 1
            remaining_messages = messages[i + 1 :]
            return get_token_count_from_usage(usage) + count_tokens_for_messages(
                remaining_messages, model
            )
    return count_tokens_for_messages(messages, model)
