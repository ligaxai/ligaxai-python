from __future__ import annotations

import logging

import pytest

from ligaxai._logging import logger, redact, setup_logging


def test_redact_authorization_values() -> None:
    assert redact("Authorization: Bearer sk-abc") == "Authorization: [redacted]"
    assert (
        redact("{'authorization': 'Bearer sk-abc', 'x': 1}")
        == "{'authorization': '[redacted]', 'x': 1}"
    )
    assert redact("nothing here") == "nothing here"


def test_setup_logging_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIGAX_LOG", "debug")
    setup_logging()
    assert logger.level == logging.DEBUG
    setup_logging("warn")
    assert logger.level == logging.WARNING
    setup_logging("nonsense")  # ignored
    assert logger.level == logging.WARNING
    setup_logging("off")
    assert logger.level > logging.CRITICAL


def test_records_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    setup_logging("debug")
    with caplog.at_level(logging.DEBUG, logger="ligaxai"):
        logger.debug("headers=%s", "Authorization: Bearer secret-token")
    assert "secret-token" not in caplog.text
    assert "[redacted]" in caplog.text
    setup_logging("off")
