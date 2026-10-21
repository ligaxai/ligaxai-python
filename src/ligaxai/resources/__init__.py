"""Endpoint namespaces. Each resource exists in a sync and an async flavour."""

from .health import AsyncHealth, Health, HealthResponse

__all__ = ["AsyncHealth", "Health", "HealthResponse"]
