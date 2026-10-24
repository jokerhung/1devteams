"""Whitelist model discovery metadata; never relay arbitrary provider payloads."""

from typing import Any
from urllib.parse import urlsplit


def reasoning_parameters(effort: str | None, format: str = "reasoning_effort") -> dict[str, Any]:
    if not effort:
        return {}
    return {"reasoning": {"effort": effort}} if format == "reasoning" else {"reasoning_effort": effort}


def model_metadata(item: dict[str, Any]) -> dict[str, Any]:
    levels = item.get("reasoning_effort_values")
    reasoning = item.get("reasoning", {})
    if isinstance(reasoning, dict) and "supported_efforts" in reasoning:
        levels = reasoning["supported_efforts"]
        if levels is None:
            levels = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    if not isinstance(levels, list):
        effort = item.get("reasoning_effort", {})
        reasoning = item.get("reasoning", {})
        if not isinstance(effort, dict):
            effort = {}
        if isinstance(reasoning, dict) and isinstance(reasoning.get("effort"), dict):
            effort = reasoning["effort"]
        levels = effort.get("enum", [])
    levels = (
        list(dict.fromkeys(value for value in levels if isinstance(value, str) and 0 < len(value) <= 100))
        if isinstance(levels, list)
        else []
    )
    supported = item.get("supported_parameters")
    if isinstance(reasoning, dict) and reasoning.get("mandatory"):
        levels = [value for value in levels if value != "none"]
    supports = bool(levels) or (
        isinstance(supported, list) and any(value in supported for value in ("reasoning", "reasoning_effort"))
    )
    return {
        "id": str(item["id"])[:100],
        "reasoning_levels": [{"id": value, "label": value} for value in levels],
        "supports_reasoning": supports if isinstance(supported, list) or levels else None,
    }


def default_reasoning_format(base_url: str) -> str:
    return "reasoning" if urlsplit(base_url).hostname == "openrouter.ai" else "reasoning_effort"
