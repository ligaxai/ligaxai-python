"""Package logger, configured from ``LIGAX_LOG``.

Nothing is emitted unless the env var is set (or the host app configures the
``ligaxai`` logger itself) — libraries must not install handlers on the
root logger. The redaction filter runs on every record so an ``Authorization`` header
never reaches a log sink, even at ``debug``.
"""

from __future__ import annotations

import logging
import os
import re

__all__ = ["logger", "redact", "setup_logging"]

LOG_ENV_VAR = "LIGAX_LOG"

logger = logging.getLogger("ligaxai")

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "off": logging.CRITICAL + 10,
}

# Matches `Authorization: Bearer xxx` / `'Authorization': 'Bearer xxx'` in any casing.
_AUTH_RE = re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)([^'\",}\s]+(?:\s+[^'\",}\s]+)?)")


# The credentials this SDK handles, wherever they appear in a message — not only after an
# `Authorization` label: keys and client tokens (`lgx_sk_…`, `lgx_pk_…`, `lgx_ct_…`) and
# webhook secrets (`whsec_…`).
_TOKEN_RE = re.compile(r"\b(lgx_(?:sk|pk|ct)_|whsec_)[A-Za-z0-9._~+/=-]+")


def redact(text: str) -> str:
    """Replace any ``Authorization`` value, and any LigaX key, token or webhook secret, in
    ``text``."""
    return _TOKEN_RE.sub(r"\1[redacted]", _AUTH_RE.sub(r"\1[redacted]", text))


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(a) if isinstance(a, str) else a for a in record.args)
        return True


def setup_logging(level: str | None = None) -> None:
    """Configure the package logger. Called once at import; safe to call again."""
    raw = (level if level is not None else os.environ.get(LOG_ENV_VAR, "off")).strip().lower()
    numeric = _LEVELS.get(raw)
    if numeric is None:
        return
    logger.setLevel(numeric)
    if not any(isinstance(f, _RedactingFilter) for f in logger.filters):
        logger.addFilter(_RedactingFilter())
    if raw != "off" and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("[%(asctime)s - %(name)s - %(levelname)s] %(message)s")
        )
        logger.addHandler(handler)


setup_logging()
