"""Redaction shared by error events, stderr and audit logs."""

import re
from typing import Any

from app.acp.types import AgentRuntimeConfig


def scrub(text: str, cfg: AgentRuntimeConfig | None = None) -> str:
    secrets = (
        (list(cfg.env.values()) + [v.get_secret_value() for v in cfg.api_params.extra_headers.values()])
        if cfg
        else []
    )
    if cfg and cfg.api_key:
        secrets.append(cfg.api_key.get_secret_value())
    for secret in sorted(secrets, key=len, reverse=True):
        if secret:
            text = text.replace(secret, "<redacted>")
    text = re.sub(r"(?i)(bearer\s+)[^\s\"'<>]+", r"\1<redacted>", text)
    text = re.sub(r"\b(?:sk-|agt_|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{6,}", "<redacted>", text)
    text = re.sub(r"(?i)(authorization[\"' ]*[:=]\s*)[^\r\n]+", r"\1<redacted>", text)
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1<redacted>@", text)
    text = re.sub(r"(?i)([?&](?:token|access_token|api_key)=)[^&\s\"]+", r"\1<redacted>", text)
    return text


def scrub_data(value: Any, cfg: AgentRuntimeConfig | None = None) -> Any:
    """Redact before JSON encoding so quotes/backslashes in credentials are safe."""
    if isinstance(value, str):
        return scrub(value, cfg)
    if isinstance(value, dict):
        return {
            scrub(str(key), cfg): "<redacted>"
            if re.fullmatch(
                r"(?i)api_key|authorization|password|secret|token|access_token|extra_headers|env|.*_enc",
                str(key),
            )
            else scrub_data(item, cfg)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [scrub_data(item, cfg) for item in value]
    return value
