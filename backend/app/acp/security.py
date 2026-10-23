"""Redaction shared by error events, stderr and audit logs."""

import re
from typing import Any

from app.acp.types import AgentRuntimeConfig


def scrub(text: str, cfg: AgentRuntimeConfig) -> str:
    secrets = list(cfg.env.values()) + [v.get_secret_value() for v in cfg.api_params.extra_headers.values()]
    if cfg.api_key:
        secrets.append(cfg.api_key.get_secret_value())
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(bearer\s+)[^\s\"'<>]+", r"\1<redacted>", text)
    text = re.sub(r"\b(?:sk-|agt_)[A-Za-z0-9_-]{10,}", "<redacted>", text)
    return text


def scrub_data(value: Any, cfg: AgentRuntimeConfig) -> Any:
    """Redact before JSON encoding so quotes/backslashes in credentials are safe."""
    if isinstance(value, str):
        return scrub(value, cfg)
    if isinstance(value, dict):
        return {scrub(str(key), cfg): scrub_data(item, cfg) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub_data(item, cfg) for item in value]
    return value
