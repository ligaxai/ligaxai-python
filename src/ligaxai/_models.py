"""Base pydantic model for every response type.

Generated models (``_generated/models.py``) and hand-written ones both inherit from
``BaseModel`` so the request pipeline can stamp ``_request_id`` on whatever it parses.
``extra="allow"`` keeps the SDK forward-compatible: a server that adds a field must not
break an older client.
"""

from __future__ import annotations

from typing import ClassVar

import pydantic
from pydantic import ConfigDict, PrivateAttr

__all__ = ["BaseModel"]


class BaseModel(pydantic.BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow", populate_by_name=True)

    _request_id: str | None = PrivateAttr(default=None)

    @property
    def request_id(self) -> str | None:
        """The ``X-Request-Id`` the server echoed for the call that produced this value."""
        return self._request_id

    def attach_request_id(self, request_id: str | None) -> None:
        """Stamp the request id on a parsed response. Called by the request pipeline."""
        self._request_id = request_id
