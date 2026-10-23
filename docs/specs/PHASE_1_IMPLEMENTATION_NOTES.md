# Phase 1 — implementation and verification

## Delivered

- `backend/app/acp/types.py`: runtime contracts, permission profiles, secret-safe API configuration.
- `jsonrpc.py`: concurrent NDJSON requests, notifications, reverse requests, timeout and EOF cleanup.
- `guard.py` / `handlers.py`: profile checks, workspace paths, sensitive file protection, permission
  choices, file diffs, terminal byte limits and process cleanup. Guard decisions log at INFO.
- `client.py`: ACP handshake, Claude config-option and Codex model selection, role prompt,
  stream mapping, modified files, cancellation, error redaction and stderr draining.
- `api_session.py` / `url_policy.py`: text-only Chat Completions SSE, in-memory conversation budget,
  usage, finish reasons, cancellation, HTTP errors, DNS validation and connection IP pinning.
- `pool.py`: ticket/agent sessions, independent ACP/API capacities, concurrent startup, idle expiry,
  config-version replacement, restart interruption and EventBus notifications.
- FastAPI lifespan owns the pool and closes it at shutdown. Agent persistence, REST management,
  websocket forwarding and engine retry integration belong to subsequent phases.
- Executable fake ACP peer, fake OpenAI app, opt-in live tests and Windows/Linux CI workflow.

## Native runtime policy gate

The Phase 0 captures show that native adapter tools do not consistently ask the ACP client for
permission. Codex `read-only` can execute read commands without `session/request_permission`;
other presets can write without the client filesystem handler. An ACP capability advertisement
does not establish enforcement of `PermissionProfile`.

Consequently, the default factory refuses to start native sessions with `RuntimePolicyError`.
`client_tools_only=True` is an integration assertion for adapters whose tool routing has been
independently verified; tests use it with the fake peer. It does not configure an adapter or
install a sandbox. `diagnostic=True` bypasses this gate only for disposable live-test workspaces.
Neither flag is exposed as an application setting or HTTP input.

**Native runtime support in the default application remains gated.** Before enabling it, establish
and verify client-mediated tool routing, or implement an external sandbox that enforces the same
filesystem, command and network policy. Shell token checks alone cannot enforce the side effects
of arbitrary Python, npm scripts or other executables; path checks also do not isolate concurrent
host processes. Diagnostic live-test success proves protocol compatibility, not sandbox coverage.

## Verification on 2026-10-22

| Check | Result |
| --- | --- |
| Windows, Python 3.12, offline suite | 87 passed, 1 skipped, 3 live tests deselected |
| Windows symlink test | Skipped because this host lacks symlink creation privilege |
| Linux Docker, Python 3.12, offline suite | 88 passed, 3 live tests deselected; lint, formatting and mypy also passed |
| Ruff lint / formatting and mypy | Passed |
| Codex ACP 2.2.2, live disposable workspace | Passed: content stream and completed directory inspection |
| Claude ACP 0.94.0, live disposable workspace | Failed: no message before 60-second prompt timeout; configured gateway TCP unavailable |
| Compatible API, fake SSE plus actual local TCP transport | Passed; actual TCP test uses a deterministic fake response |
| Compatible API, live inference endpoint | Not run: `AITEAMS_REAL_API_*` values are not configured |
| GitHub Windows/Linux CI | Workflow added; remote job has not been run in this change |

Tests also consume sanitized Phase 0 captures for both adapter handshakes and Codex notifications.
The Claude capture contains no successful inference output; it is not evidence of a full Claude turn.

## Run checks

From `backend`:

```powershell
uv sync --frozen --python 3.12
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

$env:AITEAMS_RUN_REAL_ACP='1'
uv run pytest -m real_acp
Remove-Item Env:AITEAMS_RUN_REAL_ACP

# Requires the endpoint variables described below.
uv run pytest -m real_api
```

Live ACP tests create temporary workspaces; they do not pass the repository as the agent workspace.
These tests can incur inference costs and use the existing CLI login/gateway configuration.

For live API verification, place `AITEAMS_REAL_API_BASE_URL`, `AITEAMS_REAL_API_MODEL`, and
`AITEAMS_REAL_API_KEY` in the ignored `backend/.env` or process environment. These variables are
test inputs, not persisted agent records. Credentials belong in headers, never in URL query
parameters. Azure `api-version` queries and secret `api-key` extra headers are supported.
Local endpoints require their host in **both** `API_ALLOWED_HTTP_HOSTS` and
`API_ALLOWED_PRIVATE_HOSTS`; redirects and metadata/link-local destinations remain blocked.

## Use the session pool

```python
from pathlib import Path

from app.acp.pool import ACPProcessPool
from app.acp.types import AgentRuntimeConfig


async def run(cfg: AgentRuntimeConfig, workspace: Path) -> None:
    pool = ACPProcessPool()
    try:
        session = await pool.get_or_start(cfg, workspace, ticket_id="ticket-1")
        async for event in session.prompt("Review the supplied requirements."):
            print(event.model_dump_json())
        # Use a new config_version when retrieving updated configuration from persistence.
        await pool.restart_agent(cfg.agent_id, config_version=cfg.config_version + 1)
    finally:
        await pool.close_all()
```

The default factory currently accepts the `openai-api` runtime; its profile must have
`allow_write=false`, `allow_terminal=false`, and `can_git_release=false`. The native policy gate
above applies to `codex` and `claude-code`. Runtime configuration must be reloaded by the caller
after a restart; the pool does not read a Phase 2 database that does not yet exist.

## Outstanding acceptance conditions

- Restore the configured Claude gateway and pass the live Claude test.
- Configure and verify a real compatible Chat Completions endpoint.
- Establish enforceable native tool isolation before enabling native runtimes in the default factory.
- Run the checked-in Windows/Linux workflow on GitHub. Local Linux execution is recorded separately.

The full Phase 1 Definition of Done remains open until these conditions are met.
