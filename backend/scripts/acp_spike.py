"""Run real ACP adapters in a disposable workspace, retaining full wire evidence.

Run from backend/: uv run python scripts/acp_spike.py --runtime claude
Never point an adapter at the real repository. This is a diagnostic harness, not a security sandbox.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import BACKEND_ROOT, resolve_binary  # noqa: E402

Json = dict[str, Any]


class RPCError(RuntimeError):
    pass


class Terminal:
    def __init__(self, process: asyncio.subprocess.Process, limit: int) -> None:
        self.process = process
        self.limit = limit
        self.output = b""
        self.truncated = False
        self.pump = asyncio.create_task(self.collect())

    async def collect(self) -> None:
        assert self.process.stdout is not None
        while chunk := await self.process.stdout.read(8192):
            self.output += chunk
            if len(self.output) > self.limit:
                self.output = self.output[-self.limit :] if self.limit else b""
                self.truncated = True

    async def stop(self) -> None:
        await stop_process(self.process)
        await self.pump


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        if sys.platform == "win32":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()


class SpikeClient:
    def __init__(self, process: asyncio.subprocess.Process, workspace: Path, logs: Path, stem: str) -> None:
        self.process = process
        self.workspace = workspace.resolve()
        self.pending: dict[int, asyncio.Future[Json]] = {}
        self.next_id = 0
        self.lock = asyncio.Lock()
        self.tasks: set[asyncio.Task[None]] = set()
        self.terminals: dict[str, Terminal] = {}
        self.updates: set[str] = set()
        self.message_chunks: list[str] = []
        self.calls: list[Json] = []
        self.logs: list[TextIO] = [
            (logs / f"{stem}{suffix}").open("w", encoding="utf-8")
            for suffix in (".ndjson", ".client.ndjson", ".stderr.log")
        ]
        self.reader_task = asyncio.create_task(self.read_loop())
        self.stderr_task = asyncio.create_task(self.read_stderr())

    async def send(self, message: Json) -> None:
        line = json.dumps(message, ensure_ascii=False) + "\n"
        async with self.lock:
            self.logs[1].write(line)
            self.logs[1].flush()
            assert self.process.stdin is not None
            self.process.stdin.write(line.encode("utf-8"))
            await self.process.stdin.drain()

    async def request(self, method: str, params: Json, timeout: float = 90) -> Json:
        self.next_id += 1
        request_id = self.next_id
        future: asyncio.Future[Json] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)

    async def read_loop(self) -> None:
        assert self.process.stdout is not None
        try:
            while line := await self.process.stdout.readline():
                decoded = line.decode("utf-8", errors="replace")
                self.logs[0].write(decoded)
                self.logs[0].flush()
                try:
                    message = json.loads(decoded)
                except json.JSONDecodeError:
                    continue
                if "method" in message:
                    if "id" in message:
                        task = asyncio.create_task(self.respond(message))
                        self.tasks.add(task)
                        task.add_done_callback(self.tasks.discard)
                    elif message["method"] == "session/update":
                        update = message["params"]["update"]
                        self.updates.add(update["sessionUpdate"])
                        if update["sessionUpdate"] == "agent_message_chunk":
                            content = update.get("content", {})
                            if content.get("type") == "text":
                                self.message_chunks.append(content["text"])
                else:
                    future = self.pending.get(message.get("id"))
                    if future is not None and not future.done():
                        if "error" in message:
                            future.set_exception(RPCError(json.dumps(message["error"])))
                        else:
                            future.set_result(message.get("result", {}))
        except Exception as error:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(error)
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RPCError("Adapter stdout closed before response"))

    async def read_stderr(self) -> None:
        assert self.process.stderr is not None
        while chunk := await self.process.stderr.read(8192):
            self.logs[2].write(chunk.decode("utf-8", errors="replace"))
            self.logs[2].flush()

    def safe_path(self, value: str) -> Path:
        path = (self.workspace / value).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Path is outside the disposable workspace")
        return path

    async def respond(self, message: Json) -> None:
        method, params = message["method"], message.get("params", {})
        self.calls.append({"method": method, "params": params})
        print(f"Agent request: {method}", flush=True)
        response: Json = {"jsonrpc": "2.0", "id": message["id"]}
        try:
            response["result"] = await self.handle(method, params)
        except Exception as error:
            response["error"] = {
                "code": -32601 if isinstance(error, NotImplementedError) else -32603,
                "message": str(error),
            }
        await self.send(response)

    async def handle(self, method: str, params: Json) -> Json:
        if method == "session/request_permission":
            option = next((item for item in params["options"] if item["kind"] == "allow_once"), None)
            if option is None:
                return {"outcome": {"outcome": "cancelled"}}
            return {"outcome": {"outcome": "selected", "optionId": option["optionId"]}}
        if method == "fs/read_text_file":
            lines = self.safe_path(params["path"]).read_text(encoding="utf-8").splitlines(keepends=True)
            start = max(0, params.get("line", 1) - 1)
            stop = start + params["limit"] if params.get("limit") is not None else None
            return {"content": "".join(lines[start:stop])}
        if method == "fs/write_text_file":
            path = self.safe_path(params["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(params["content"], encoding="utf-8")
            return {}
        if method == "terminal/create":
            cwd = self.safe_path(params.get("cwd") or str(self.workspace))
            env = os.environ | {item["name"]: item["value"] for item in params.get("env", [])}
            process = await asyncio.create_subprocess_exec(
                params["command"],
                *params.get("args", []),
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            terminal_id = str(len(self.terminals) + 1)
            self.terminals[terminal_id] = Terminal(process, params.get("outputByteLimit") or 1024 * 1024)
            return {"terminalId": terminal_id}
        if method.startswith("terminal/"):
            terminal = self.terminals[params["terminalId"]]
            if method == "terminal/output":
                result: Json = {
                    "output": terminal.output.decode("utf-8", errors="ignore"),
                    "truncated": terminal.truncated,
                }
                if terminal.process.returncode is not None:
                    result["exitStatus"] = {"exitCode": terminal.process.returncode}
                return result
            if method == "terminal/wait_for_exit":
                code = await terminal.process.wait()
                await terminal.pump
                return {"exitCode": code}
            if method in ("terminal/kill", "terminal/release"):
                await terminal.stop()
                if method == "terminal/release":
                    del self.terminals[params["terminalId"]]
                return {}
        raise NotImplementedError(f"Unsupported client request: {method}")

    async def close(self) -> None:
        for terminal in self.terminals.values():
            await terminal.stop()
        await stop_process(self.process)
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await asyncio.gather(self.reader_task, self.stderr_task, return_exceptions=True)
        for log in self.logs:
            log.close()


async def run(args: argparse.Namespace) -> int:
    binary = resolve_binary(args.binary or {"claude": "claude-agent-acp", "codex": "codex-acp"}[args.runtime])
    if binary is None:
        raise SystemExit("Adapter not found. Run npm install at the repository root first.")
    logs = Path(args.log_dir).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    stem = f"{args.runtime}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
    # Retain the tiny workspace for inspection; its path is recorded in the summary.
    workspace = Path(tempfile.mkdtemp(prefix=f"aiteams_{args.runtime}_"))
    (workspace / "src").mkdir()
    (workspace / "src" / "example.py").write_text('print("aiTeams spike")\n', encoding="utf-8")
    (workspace / "README.md").write_text("Disposable aiTeams ACP spike workspace.\n", encoding="utf-8")
    command = [binary, *args.adapter_arg]
    if sys.platform == "win32" and Path(binary).suffix.lower() in (".cmd", ".bat"):
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", *command]
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=workspace,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=16 * 1024 * 1024,
    )
    client = SpikeClient(process, workspace, logs, stem)
    summary: Json = {"runtime": args.runtime, "binary": binary, "workspace": str(workspace)}
    try:
        summary["initialize"] = await client.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": True, "writeTextFile": True}, "terminal": True},
                "clientInfo": {"name": "aiteams", "version": "0.1.0"},
            },
        )
        new_params: Json = {"cwd": str(workspace), "mcpServers": []}
        role = "You are a BA. When asked your role, reply exactly: AITEAMS_BA_SPIKE."
        if args.runtime == "claude":
            new_params["_meta"] = {"systemPrompt": {"append": role}}
            if args.isolate_settings:
                new_params["_meta"]["claudeCode"] = {"options": {"settingSources": []}}
        session = summary["session_new"] = await client.request("session/new", new_params)
        session_id = session["sessionId"]
        if args.mode:
            summary["set_mode"] = await client.request(
                "session/set_mode",
                {
                    "sessionId": session_id,
                    "modeId": args.mode,
                },
            )
        models = session.get("models", {})
        model_option: Json = next(
            (item for item in session.get("configOptions", []) if item["id"] == "model"), {}
        )
        model = args.model or models.get("currentModelId") or model_option.get("currentValue")
        if model:
            try:
                method = (
                    "session/set_config_option"
                    if model_option and args.runtime == "claude"
                    else "session/set_model"
                )
                model_params = (
                    {"configId": "model", "value": model}
                    if method.endswith("config_option")
                    else {"modelId": model}
                )
                summary["set_model"] = await client.request(
                    method,
                    {"sessionId": session_id, **model_params},
                )
                summary["model_method"] = method
                summary["selected_model"] = model
            except RPCError as error:
                summary["set_model_error"] = str(error)

        async def prompt(text: str) -> Json:
            return await client.request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
                args.timeout,
            )

        prefix = f"{role}\n\n" if args.runtime == "codex" else ""
        if not args.cancel_only:
            first_chunk = len(client.message_chunks)
            summary["prompt"] = await prompt(
                prefix
                + "List the files in src, read src/example.py, and create hello.txt containing exactly "
                "hello from aiTeams. Use your tools, only within this disposable workspace. "
                "Do not modify any other files. Then answer: what is your role?"
            )
            summary["hello_exists"] = (workspace / "hello.txt").is_file()
            try:
                summary["hello_content"] = (
                    (workspace / "hello.txt").read_text() if summary["hello_exists"] else None
                )
            except OSError as error:
                summary["hello_read_error"] = str(error)
            summary["hello_verified"] = summary.get("hello_content", "").strip() == "hello from aiTeams"
            summary["role_verified"] = "AITEAMS_BA_SPIKE" in "".join(client.message_chunks[first_chunk:])
        if not args.skip_cancel:
            pending = asyncio.create_task(
                prompt(
                    "Use a terminal to run a command that waits 30 seconds, then list src again. "
                    "Do not modify files."
                )
            )
            await asyncio.sleep(args.cancel_after)
            summary["cancel_sent_while_pending"] = not pending.done()
            await client.send(
                {"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}}
            )
            try:
                summary["cancel_result"] = await asyncio.wait_for(pending, 30)
            except (RPCError, TimeoutError) as error:
                summary["cancel_error"] = str(error)
    except Exception as error:
        summary["error"] = f"{type(error).__name__}: {error}"
    finally:
        await client.close()
        summary["session_updates"] = sorted(client.updates)
        summary["client_requests"] = client.calls
        checks = {"model_selection": "set_model" in summary}
        if not args.cancel_only:
            checks.update(
                {
                    "prompt_completed": summary.get("prompt", {}).get("stopReason") == "end_turn",
                    "hello_content": summary.get("hello_verified") is True,
                    "role_instruction": summary.get("role_verified") is True,
                }
            )
        if not args.skip_cancel:
            checks["cancellation"] = (
                summary.get("cancel_sent_while_pending") is True
                and summary.get("cancel_result", {}).get("stopReason") == "cancelled"
            )
        summary["checks"] = checks
        summary["passed"] = all(checks.values()) and "error" not in summary
        (logs / f"{stem}.summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "log": str(logs / f"{stem}.ndjson"),
                "error": summary.get("error"),
                "hello_exists": summary.get("hello_exists"),
                "checks": summary["checks"],
                "passed": summary["passed"],
                "updates": summary["session_updates"],
            }
        ),
        flush=True,
    )
    return 0 if summary["passed"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", choices=["claude", "codex"], required=True)
    parser.add_argument("--binary", help="Override adapter binary")
    parser.add_argument(
        "--adapter-arg", action="append", default=[], help="Adapter argument (use = for flags)"
    )
    parser.add_argument("--model", help="Model ID; by default re-select the model returned by session/new")
    parser.add_argument("--mode", help="Explicit adapter permission mode ID from session/new")
    parser.add_argument(
        "--isolate-settings",
        action="store_true",
        help="Claude: ignore user/project settings for this session",
    )
    parser.add_argument("--log-dir", default=str(BACKEND_ROOT / "spike_logs"))
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--cancel-after", type=float, default=2)
    parser.add_argument("--skip-cancel", action="store_true")
    parser.add_argument("--cancel-only", action="store_true", help="Probe cancellation without file creation")
    args = parser.parse_args()
    if args.skip_cancel and args.cancel_only:
        parser.error("--skip-cancel and --cancel-only cannot be combined")
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    with contextlib.suppress(KeyboardInterrupt):
        raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
