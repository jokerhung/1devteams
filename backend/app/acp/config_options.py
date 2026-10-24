"""Normalize advertised ACP selectors, including older model[effort] adapters."""

import re
from typing import Any


def choices(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        value for item in options for value in (choices(item["options"]) if "options" in item else [item])
    ]


def selector(options: list[dict[str, Any]], category: str) -> dict[str, Any]:
    return next(
        (item for item in options if item.get("category") == category),
        next(
            (
                item
                for item in options
                if item.get("id")
                in (("model",) if category == "model" else ("effort", "reasoning_effort", "thought_level"))
            ),
            {},
        ),
    )


def split_model(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"(.+)\[([^\[\]]+)\]", value)
    return (match[1], match[2]) if match else (value, "")


def describe(options: list[dict[str, Any]], legacy: list[dict[str, Any]]) -> dict[str, Any]:
    model = selector(options, "model")
    effort = selector(options, "thought_level")
    models: dict[str, dict[str, Any]] = {}
    for item in choices(model.get("options", [])) if model else legacy:
        value = item.get("value") or item.get("modelId") or item.get("id")
        if not isinstance(value, str):
            continue
        base, level = split_model(value) if not effort else (value, "")
        label = item.get("name", base)
        if level:
            label = re.sub(r"\s*\([^()]*\)$", "", label)
        entry = models.setdefault(base, {"id": base, "label": label, "reasoning_levels": []})
        if level:
            entry["reasoning_levels"].append({"id": level, "label": level})
    return {
        "models": list(models.values()),
        "reasoning_levels": [
            {"id": item["value"], "label": item.get("name", item["value"])}
            for item in choices(effort.get("options", []))
            if "value" in item
        ],
        "current_reasoning": effort.get("currentValue"),
    }
