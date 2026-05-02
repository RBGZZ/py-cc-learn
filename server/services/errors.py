from __future__ import annotations

import re
from enum import Enum

API_ERROR_MESSAGE_PREFIX = "API Error"
PROMPT_TOO_LONG_ERROR_MESSAGE = "Prompt is too long"
CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE = "Credit balance is too low"
INVALID_API_KEY_ERROR_MESSAGE = "Not logged in · Please run /login"
INVALID_API_KEY_ERROR_MESSAGE_EXTERNAL = "Invalid API key · Fix external API key"
ORG_DISABLED_ERROR_MESSAGE_ENV_KEY_WITH_OAUTH = (
    "Your ANTHROPIC_API_KEY belongs to a disabled organization · "
    "Unset the environment variable to use your subscription instead"
)
ORG_DISABLED_ERROR_MESSAGE_ENV_KEY = (
    "Your ANTHROPIC_API_KEY belongs to a disabled organization · "
    "Update or unset the environment variable"
)
TOKEN_REVOKED_ERROR_MESSAGE = "OAuth token revoked · Please run /login"
CCR_AUTH_ERROR_MESSAGE = (
    "Authentication error · This may be a temporary network issue, please try again"
)
REPEATED_529_ERROR_MESSAGE = "Repeated 529 Overloaded errors"
CUSTOM_OFF_SWITCH_MESSAGE = "Opus is experiencing high load, please use /model to switch to Sonnet"
API_TIMEOUT_ERROR_MESSAGE = "Request timed out"
NO_RESPONSE_REQUESTED = "__no_response_requested__"
OAUTH_ORG_NOT_ALLOWED_ERROR_MESSAGE = (
    "Your account does not have access to Claude Code. Please run /login."
)

API_PDF_MAX_PAGES = 100
PDF_TARGET_RAW_SIZE = 32 * 1024 * 1024


def starts_with_api_error_prefix(text: str) -> bool:
    return text.startswith(API_ERROR_MESSAGE_PREFIX) or text.startswith(
        f"Please run /login · {API_ERROR_MESSAGE_PREFIX}"
    )


def is_prompt_too_long_message(content_blocks: list[dict]) -> bool:
    return any(
        block.get("type") == "text"
        and block.get("text", "").startswith(PROMPT_TOO_LONG_ERROR_MESSAGE)
        for block in content_blocks
    )


def parse_prompt_too_long_token_counts(raw_message: str) -> tuple[int | None, int | None]:
    match = re.search(
        r"prompt is too long[^0-9]*(\d+)\s*tokens?\s*>\s*(\d+)", raw_message, re.IGNORECASE
    )
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def get_prompt_too_long_token_gap(error_details: str | None) -> int | None:
    if not error_details:
        return None
    actual, limit = parse_prompt_too_long_token_counts(error_details)
    if actual is None or limit is None:
        return None
    gap = actual - limit
    return gap if gap > 0 else None


def is_media_size_error(raw: str) -> bool:
    return (
        ("image exceeds" in raw and "maximum" in raw)
        or ("image dimensions exceed" in raw and "many-image" in raw)
        or bool(re.search(r"maximum of \d+ PDF pages", raw))
    )


def get_pdf_too_large_error_message(is_non_interactive: bool = False) -> str:
    limits = f"max {API_PDF_MAX_PAGES} pages, {_format_pdf_size(PDF_TARGET_RAW_SIZE)}"
    if is_non_interactive:
        return f"PDF too large ({limits}). Try reading the file a different way (e.g., extract text with pdftotext)."
    return f"PDF too large ({limits}). Double press esc to go back and try again, or use pdftotext to convert to text first."


def get_pdf_password_protected_error_message(is_non_interactive: bool = False) -> str:
    if is_non_interactive:
        return "PDF is password protected. Try using a CLI tool to extract or convert the PDF."
    return "PDF is password protected. Please double press esc to edit your message and try again."


def get_pdf_invalid_error_message(is_non_interactive: bool = False) -> str:
    if is_non_interactive:
        return "The PDF file was not valid. Try converting it to text first (e.g., pdftotext)."
    return "The PDF file was not valid. Double press esc to go back and try again with a different file."


def get_image_too_large_error_message(is_non_interactive: bool = False) -> str:
    if is_non_interactive:
        return "Image was too large. Try resizing the image or using a different approach."
    return "Image was too large. Double press esc to go back and try again with a smaller image."


def get_request_too_large_error_message(is_non_interactive: bool = False) -> str:
    limits = f"max {_format_pdf_size(PDF_TARGET_RAW_SIZE)}"
    if is_non_interactive:
        return f"Request too large ({limits}). Try with a smaller file."
    return f"Request too large ({limits}). Double press esc to go back and try with a smaller file."


def get_token_revoked_error_message(is_non_interactive: bool = False) -> str:
    if is_non_interactive:
        return "Your account does not have access to Claude. Please login again or contact your administrator."
    return TOKEN_REVOKED_ERROR_MESSAGE


def get_oauth_org_not_allowed_error_message(is_non_interactive: bool = False) -> str:
    if is_non_interactive:
        return "Your organization does not have access to Claude. Please login again or contact your administrator."
    return OAUTH_ORG_NOT_ALLOWED_ERROR_MESSAGE


def _format_pdf_size(size: int) -> str:
    return f"{size / (1024 * 1024):.0f}MB"


class APIErrorType(str, Enum):
    TIMEOUT = "api_timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_OVERLOAD = "server_overload"
    REPEATED_529 = "repeated_529"
    CAPACITY_OFF_SWITCH = "capacity_off_switch"
    PROMPT_TOO_LONG = "prompt_too_long"
    PDF_TOO_LARGE = "pdf_too_large"
    PDF_PASSWORD_PROTECTED = "pdf_password_protected"
    IMAGE_TOO_LARGE = "image_too_large"
    TOOL_USE_MISMATCH = "tool_use_mismatch"
    UNEXPECTED_TOOL_RESULT = "unexpected_tool_result"
    DUPLICATE_TOOL_USE_ID = "duplicate_tool_use_id"
    INVALID_MODEL = "invalid_model"
    CREDIT_BALANCE_LOW = "credit_balance_low"
    AUTH_ERROR = "auth_error"
    INVALID_API_KEY = "invalid_api_key"
    TOKEN_REVOKED = "token_revoked"
    OAUTH_ORG_NOT_ALLOWED = "oauth_org_not_allowed"
    BEDROCK_MODEL_ACCESS = "bedrock_model_access"
    CONNECTION_ERROR = "connection_error"
    SSL_CERT_ERROR = "ssl_cert_error"
    ABORTED = "aborted"
    SERVER_ERROR = "server_error"
    CLIENT_ERROR = "client_error"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    def __init__(self, message: str, error_type: APIErrorType = APIErrorType.UNKNOWN):
        super().__init__(message)
        self.error_type = error_type


class CannotRetryError(Exception):
    def __init__(self, original_error: Exception, model: str = ""):
        super().__init__(str(original_error))
        self.original_error = original_error
        self.model = model


class FallbackTriggeredError(Exception):
    def __init__(self, original_model: str, fallback_model: str):
        super().__init__(f"Model fallback triggered: {original_model} -> {fallback_model}")
        self.original_model = original_model
        self.fallback_model = fallback_model


class APIOverloadedError(ProviderError):
    def __init__(self, message: str = "Server is overloaded"):
        super().__init__(message, APIErrorType.SERVER_OVERLOAD)


class APIRateLimitError(ProviderError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message, APIErrorType.RATE_LIMIT)


class APIAuthenticationError(ProviderError):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, APIErrorType.AUTH_ERROR)


class APITimeoutError(ProviderError):
    def __init__(self, message: str = "Request timed out"):
        super().__init__(message, APIErrorType.TIMEOUT)


def classify_api_error(error: Exception) -> str:
    msg = str(error)
    msg_lower = msg.lower()

    if "request was aborted" in msg_lower:
        return APIErrorType.ABORTED

    if "timeout" in msg_lower or "timed out" in msg_lower:
        return APIErrorType.TIMEOUT

    if REPEATED_529_ERROR_MESSAGE in msg:
        return APIErrorType.REPEATED_529

    if CUSTOM_OFF_SWITCH_MESSAGE in msg:
        return APIErrorType.CAPACITY_OFF_SWITCH

    if _is_overloaded_error(error):
        return APIErrorType.SERVER_OVERLOAD

    if _is_rate_limit_error(error):
        return APIErrorType.RATE_LIMIT

    if PROMPT_TOO_LONG_ERROR_MESSAGE.lower() in msg_lower:
        return APIErrorType.PROMPT_TOO_LONG

    if re.search(r"maximum of \d+ PDF pages", msg):
        return APIErrorType.PDF_TOO_LARGE

    if "pdf specified is password protected" in msg_lower:
        return APIErrorType.PDF_PASSWORD_PROTECTED

    if "image exceeds" in msg_lower and "maximum" in msg_lower:
        return APIErrorType.IMAGE_TOO_LARGE

    if "image dimensions exceed" in msg_lower and "many-image" in msg_lower:
        return APIErrorType.IMAGE_TOO_LARGE

    if "`tool_use` ids were found without `tool_result` blocks immediately after" in msg_lower:
        return APIErrorType.TOOL_USE_MISMATCH

    if "unexpected `tool_use_id` found in `tool_result`" in msg_lower:
        return APIErrorType.UNEXPECTED_TOOL_RESULT

    if "`tool_use` ids must be unique" in msg_lower:
        return APIErrorType.DUPLICATE_TOOL_USE_ID

    if "invalid model name" in msg_lower:
        return APIErrorType.INVALID_MODEL

    if CREDIT_BALANCE_TOO_LOW_ERROR_MESSAGE.lower() in msg_lower:
        return APIErrorType.CREDIT_BALANCE_LOW

    if "x-api-key" in msg_lower:
        return APIErrorType.INVALID_API_KEY

    if "oauth token has been revoked" in msg_lower:
        return APIErrorType.TOKEN_REVOKED

    if "oauth authentication is currently not allowed" in msg_lower:
        return APIErrorType.OAUTH_ORG_NOT_ALLOWED

    status = _extract_http_status(error)
    if status is not None:
        if status == 401 or status == 403:
            return APIErrorType.AUTH_ERROR
        if status >= 500:
            return APIErrorType.SERVER_ERROR
        if status >= 400:
            return APIErrorType.CLIENT_ERROR

    if "connection" in msg_lower or "econnrefused" in msg_lower or "econnreset" in msg_lower:
        return APIErrorType.CONNECTION_ERROR

    return APIErrorType.UNKNOWN


def _is_overloaded_error(error: Exception) -> bool:
    msg = str(error)
    return '"type":"overloaded_error"' in msg


def _is_rate_limit_error(error: Exception) -> bool:
    msg = str(error)
    return "429" in msg and ("rate" in msg.lower() or "quota" in msg.lower())


def _extract_http_status(error: Exception) -> int | None:
    for attr in ("status_code", "status", "http_status"):
        val = getattr(error, attr, None)
        if isinstance(val, int):
            return val
    return None


def categorize_retryable_api_error(status: int, message: str) -> str:
    if status == 529 or '"type":"overloaded_error"' in message:
        return APIErrorType.RATE_LIMIT
    if status == 429:
        return APIErrorType.RATE_LIMIT
    if status in (401, 403):
        return APIErrorType.AUTH_ERROR
    if status >= 408:
        return APIErrorType.SERVER_ERROR
    return APIErrorType.UNKNOWN
