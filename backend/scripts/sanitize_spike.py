"""Export real ACP wire logs with local identities and credentials removed.

Usage: uv run python scripts/sanitize_spike.py spike_logs/<stem>.ndjson tests/fixtures/acp/claude.ndjson
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


def sanitize(value: Any, replacements: dict[str, str], ids: dict[str, str]) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key.lower() in {"apikey", "api_key", "token", "accesstoken", "authorization", "email"}:
                result[key] = "<REDACTED>"
            elif key in {"sessionId", "messageId", "toolCallId", "terminalId"} and isinstance(item, str):
                result[key] = ids.setdefault(item, f"{key}-{len(ids) + 1}")
            else:
                result[key] = sanitize(item, replacements, ids)
        return result
    if isinstance(value, list):
        return [sanitize(item, replacements, ids) for item in value]
    if isinstance(value, str):
        for source, target in sorted(ids.items(), key=lambda pair: len(pair[0]), reverse=True):
            value = value.replace(source, target)
        for source, target in sorted(replacements.items(), key=lambda pair: len(pair[0]), reverse=True):
            value = value.replace(source, target)
        value = re.sub(
            r"\b[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\b",
            lambda match: ids.setdefault(match[0], f"id-{len(ids) + 1}"),
            value,
        )
        value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<EMAIL>", value)
        value = re.sub(r"\b(?:sk-|agt_)[A-Za-z0-9_-]{12,}", "<REDACTED>", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    summary = json.loads(args.source.with_suffix(".summary.json").read_text(encoding="utf-8"))
    replacements = {summary["workspace"]: "C:\\spike\\workspace", str(Path.home()): "C:\\Users\\test-user"}
    for key, value in os.environ.items():
        if (
            any(part in key.upper() for part in ("TOKEN", "SECRET", "API_KEY", "BASE_URL"))
            and len(value) >= 8
        ):
            replacements[value] = "<REDACTED>"
    for source, target in list(replacements.items()):
        replacements[source.replace("\\", "\\\\")] = target.replace("\\", "\\\\")
        replacements[source.replace("\\", "/")] = target.replace("\\", "/")
    ids: dict[str, str] = {}
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".ndjson", ".client.ndjson"):
        source_path = args.source.with_name(args.source.stem + suffix)
        destination = args.destination.with_name(args.destination.stem + suffix)
        with destination.open("w", encoding="utf-8") as output:
            for line in source_path.read_text(encoding="utf-8").splitlines():
                output.write(
                    json.dumps(sanitize(json.loads(line), replacements, ids), ensure_ascii=False) + "\n"
                )
    print(f"Exported {args.destination.name} and client transcript; review before committing.")


if __name__ == "__main__":
    main()
