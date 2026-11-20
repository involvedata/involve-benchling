"""Describe SDK errors safely, for logs and status records."""

from __future__ import annotations

from typing import Any

from benchling_v3_sdk.core.api_error import ApiError
from benchling_v3_sdk.core.parse_error import ParsingError

__all__ = ["describe_error"]


def describe_error(e: BaseException) -> str:
    """Return one line naming the exception type and what went wrong.

    SDK API and parsing errors stringify with every response header, session
    cookie included, so they are reduced to status code and Benchling's message,
    e.g. ``ApiError: HTTP 403: Not allowed (invalid_request_error)``.
    """
    if isinstance(e, (ApiError, ParsingError)):
        return f"{type(e).__name__}: HTTP {e.status_code}: {_api_message(e.body)}"
    return f"{type(e).__name__}: {e}"


def _api_message(body: Any) -> str:
    if hasattr(body, "model_dump"):
        body = body.model_dump(mode="json", by_alias=True)
    if not isinstance(body, dict):
        return str(body)
    error = body.get("error")
    if isinstance(error, dict) and error.get("message"):
        return f"{error['message']} ({error.get('type')})"
    return str(body.get("detail") or body.get("title") or body)
