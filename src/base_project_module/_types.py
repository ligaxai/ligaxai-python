"""Shared type aliases and the ``NotGiven`` sentinel.

``NOT_GIVEN`` lets a caller distinguish "I did not pass this argument" from "I passed
``None``" — the same pattern the OpenAI and Anthropic SDKs use, so ``with_options`` can
override only the fields that were actually supplied.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias, TypeVar

import httpx2

__all__ = [
    "NOT_GIVEN",
    "Headers",
    "NotGiven",
    "NotGivenOr",
    "Query",
    "RequestOptions",
    "Timeout",
]

T = TypeVar("T")


class NotGiven:
    """Sentinel type for "argument not supplied". Falsy; compare with ``is NOT_GIVEN``."""

    _instance: NotGiven | None = None

    def __new__(cls) -> NotGiven:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN = NotGiven()

NotGivenOr: TypeAlias = T | NotGiven

Headers: TypeAlias = Mapping[str, str]
Query: TypeAlias = Mapping[str, Any]
Timeout: TypeAlias = httpx2.Timeout


@dataclass(slots=True)
class RequestOptions:
    """Per-request overrides accepted by every resource method.

    ``max_retries`` / ``timeout`` fall back to the client defaults when left ``None``;
    ``idempotency_key`` overrides the UUID the pipeline would otherwise mint for a POST.
    """

    headers: dict[str, str] = field(default_factory=dict[str, str])
    params: dict[str, Any] = field(default_factory=dict[str, Any])
    timeout: httpx2.Timeout | float | None = None
    max_retries: int | None = None
    idempotency_key: str | None = None
