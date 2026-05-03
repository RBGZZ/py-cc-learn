"""Security utilities: prompt injection detection, input sanitization."""
from __future__ import annotations

import re

# Patterns that indicate potential prompt injection attempts
INJECTION_PATTERNS = [
    re.compile(r"</system>", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"ignore all (previous|prior) instructions", re.IGNORECASE),
    re.compile(r"forget (all|everything) (above|before)", re.IGNORECASE),
    re.compile(r"you are now", re.IGNORECASE),
    re.compile(r"new system prompt", re.IGNORECASE),
]

MAX_PROMPT_LENGTH = 200_000
MAX_PROMPT_WARNING_LENGTH = 100_000


def detect_injection(text: str) -> list[str]:
    """Detect potential prompt injection patterns in user input.
    
    Returns list of matched pattern descriptions (empty list if clean).
    """
    if not text:
        return []
    detected = []
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            detected.append(f"Potential injection: pattern '{pattern.pattern}' matched")
    return detected


def is_prompt_safe(text: str) -> tuple[bool, str]:
    """Check if a prompt is safe to process.
    
    Returns (is_safe, reason).
    """
    if not text or not text.strip():
        return False, "Prompt is empty"
    
    if len(text) > MAX_PROMPT_LENGTH:
        return False, f"Prompt exceeds maximum length ({MAX_PROMPT_LENGTH} chars)"
    
    injections = detect_injection(text)
    if injections:
        return False, f"Injection detected: {'; '.join(injections)}"
    
    return True, "OK"


def sanitize_prompt(text: str) -> str:
    """Sanitize user prompt by stripping dangerous control sequences."""
    if not text:
        return text
    # Strip null bytes
    text = text.replace("\x00", "")
    return text[:MAX_PROMPT_LENGTH]
