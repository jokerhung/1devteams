"""Executable scripted ACP peer; scenarios are explicit expectations, not an LLM."""

import json
import sys
from pathlib import Path


def send(message):
    print(json.dumps({"jsonrpc": "2.0", **message}), flush=True)


def read():
    line = sys.stdin.readline()
    if not line:
        raise SystemExit(0)
    return json.loads(line)


def main():
    scenario = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for step in scenario:
        message = read()
        assert message.get("method") == step["expect"], (message, step)
        params = message.get("params", {})
        for key, expected in step.get("assert_params", {}).items():
            assert params[key] == expected
        if prefix := step.get("assert_prompt_prefix"):
            assert params["prompt"][0]["text"].startswith(prefix)
        if step.get("assert_no_role"):
            assert not params["prompt"][0]["text"].startswith("[SYSTEM ROLE]")
        if "assert_image_count" in step:
            images = [item for item in params["prompt"] if item["type"] == "image"]
            assert len(images) == step["assert_image_count"], images
            assert all(image.get("data") and image.get("mimeType") == "image/png" for image in images)
        if step.get("junk"):
            print("not json", flush=True)
            print("[]", flush=True)
        if step.get("stderr"):
            print(step["stderr"], file=sys.stderr, flush=True)
        if step.get("exit"):
            return
        for index, action in enumerate(step.get("then", [])):
            if "notify" in action:
                send({"method": action["notify"], "params": action["params"]})
            else:
                send({"id": f"agent-{index}", "method": action["request"], "params": action["params"]})
                response = read()
                assert response["id"] == f"agent-{index}", response
                if "assert_option" in action:
                    assert response["result"]["outcome"]["optionId"] == action["assert_option"], response
                if "assert_error" in action:
                    assert response["error"]["code"] == action["assert_error"], response
        if step.get("wait_for_cancel"):
            cancel = read()
            assert cancel["method"] == "session/cancel", cancel
            if marker := step.get("cancel_marker"):
                Path(marker).write_text("cancelled", encoding="utf-8")
        if "error" in step:
            send({"id": message["id"], "error": step["error"]})
        elif "id" in message:
            send({"id": message["id"], "result": step.get("reply", {})})
    # Keep stdout open until the client closes it, like a real adapter.
    for _ in sys.stdin:
        pass


if __name__ == "__main__":
    main()
