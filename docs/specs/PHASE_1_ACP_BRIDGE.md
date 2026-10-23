# PHASE 1 — ACP Subprocess Bridge & Dynamic Permission Guard

## 1. Mục tiêu
Xây module Python `app/acp/` để:
1. Spawn và quản lý vòng đời `claude-agent-acp` / `codex-acp` qua stdio (JSON-RPC 2.0, NDJSON).
2. Phục vụ các request agent gửi ngược về client: `session/request_permission`, `fs/read_text_file`, `fs/write_text_file`, `terminal/*`.
3. Enforce quyền theo `PermissionProfile` của agent (không hard-code 4 role).
4. Chuẩn hóa mọi thứ thành `ACPStreamEvent` dạng async generator để Engine (Phase 3) tiêu thụ.

> Đọc `docs/specs/ACP_SPIKE_NOTES.md` (Phase 0) trước. Chỗ nào spec dưới đây khác thực tế đã ghi nhận → **làm theo spike notes** và ghi chú lệch.

## 2. Cấu trúc file
```text
backend/app/acp/
├── __init__.py
├── types.py        # Pydantic models
├── jsonrpc.py      # JsonRpcConnection: đọc/ghi NDJSON, map id → Future, dispatch request/notification
├── guard.py        # DynamicPermissionGuard
├── handlers.py     # ClientRequestHandlers: fs/*, terminal/* (sandbox workspace)
├── client.py       # ACPSession / ACPSubprocessClient
└── pool.py         # ACPProcessPool: tái sử dụng process theo (agent_id, workspace)
backend/tests/acp/
├── fake_agent.py   # ACP agent giả (đọc kịch bản NDJSON từ fixtures) để test không cần CLI thật
├── test_jsonrpc.py
├── test_guard.py
├── test_handlers.py
├── test_client_fake.py
└── test_client_real.py   # @pytest.mark.real_acp — chỉ chạy khi có CLI đã login
```

## 3. Đặc tả

### 3.1. `types.py`
```python
RuntimeType = Literal["claude-code", "codex"]

class PermissionProfile(BaseModel):
    allow_read: bool = True
    allow_write: bool = False
    allow_terminal: bool = False
    allowed_commands: list[str] = []          # nếu khác rỗng: CHỈ cho phép lệnh bắt đầu bằng các prefix này
    blocked_commands: list[str] = ["git commit", "git push", "git reset --hard", "rm -rf"]
    can_git_release: bool = False              # chỉ dùng ở Phase 3 (GitService)

class AgentRuntimeConfig(BaseModel):
    agent_id: str
    handle: str                 # "@developer"
    runtime: RuntimeType
    model: str | None
    system_prompt: str
    permission_profile: PermissionProfile
    env: dict[str, str] = {}    # biến môi trường bổ sung (không log)

ACPEventType = Literal["message_chunk","thought_chunk","tool_call","tool_call_update","file_edit",
                       "terminal_output","permission","plan","completed","error"]

class ACPStreamEvent(BaseModel):
    agent_handle: str
    event_type: ACPEventType
    content: str = ""
    metadata: dict[str, Any] = {}

class PromptResult(BaseModel):
    stop_reason: str            # end_turn | max_tokens | refusal | cancelled | ...
    full_text: str              # ghép toàn bộ message_chunk
    modified_files: list[str]   # tổng hợp từ fs/write_text_file + tool_call kind=edit
```

### 3.2. `jsonrpc.py` — `JsonRpcConnection`
- Constructor nhận `reader: asyncio.StreamReader`, `writer: asyncio.StreamWriter`.
- `async def request(method, params, timeout) -> dict`: tăng id, đăng ký `Future`, ghi `json.dumps(...)+"\n"`, chờ.
- `async def notify(method, params)`.
- `async def respond(id, result=None, error=None)`.
- Task nền `_read_loop()`:
  - Đọc từng dòng; bỏ qua dòng rỗng/không phải JSON (log warning, **không crash**). Dùng `reader.readline()` với `limit` lớn (≥ 16 MB, set khi tạo subprocess) vì diff/file có thể dài.
  - Có `id` + (`result`|`error`) → resolve Future.
  - Có `method` + `id` → request từ agent → `await self.on_request(method, params)` → `respond`.
  - Có `method`, không `id` → notification → `await self.on_notification(method, params)`.
  - EOF → reject mọi Future đang chờ bằng `ACPProcessExited`.
- Lock ghi (`asyncio.Lock`) để tránh xen kẽ dòng.

### 3.3. `guard.py` — `DynamicPermissionGuard`
```python
class Decision(BaseModel):
    allowed: bool
    reason: str

class DynamicPermissionGuard:
    def __init__(self, profile: PermissionProfile, workspace: Path): ...
    def check_read(self, path: str) -> Decision
    def check_write(self, path: str) -> Decision
    def check_command(self, command: str, args: list[str] | None = None) -> Decision
    def evaluate_permission_request(self, params: dict) -> Decision   # cho session/request_permission
```
Luật:
1. **Path sandbox**: resolve tuyệt đối (`Path.resolve()`, chuẩn hóa hoa/thường trên Windows), phải nằm trong `workspace`. Chặn `..`, symlink trỏ ra ngoài, các file nhạy cảm `.env*`, `*.pem`, `id_rsa*` (đọc vẫn chặn với `.env`).
2. `check_read` → `allow_read`.
3. `check_write` → `allow_write` + sandbox. Chặn ghi vào `.git/`.
4. `check_command`:
   - `allow_terminal == False` → deny.
   - Chuẩn hóa lệnh: gộp `command + args`, lowercase, rút gọn khoảng trắng; tách theo `&&`, `||`, `;`, `|`, newline, và nội dung trong `$(...)`/backtick → kiểm tra **từng đoạn**.
   - Nếu đoạn nào match `blocked_commands` (so khớp theo token, VD `git  -c x=y commit` vẫn tính là `git commit`: bỏ các option `-c k=v`, `-C path` giữa `git` và subcommand) → deny.
   - Nếu `allowed_commands` khác rỗng và đoạn không bắt đầu bằng prefix nào → deny.
5. `evaluate_permission_request(params)`:
   - Lấy `toolCall.kind` (`read` | `edit` | `delete` | `move` | `execute` | `search` | `fetch` | `think` | `other`), `toolCall.rawInput`, `toolCall.locations[].path`, `toolCall.title`.
   - `read`/`search` → check_read; `edit`/`delete`/`move` → check_write cho mọi location; `execute` → check_command(rawInput.command); `fetch` → deny mặc định (cấu hình được); `other`/không rõ → deny + log để bổ sung luật.
6. Trả về `Decision` có `reason` rõ ràng (dùng để hiển thị trong log terminal UI: `Guard: Blocked git commit for @developer`).

**Chọn optionId**: hàm tiện ích `pick_option(options, allowed)` → nếu allowed chọn option `kind == "allow_once"` (fallback `allow_always` — KHÔNG ưu tiên always); nếu deny chọn `reject_once` (fallback `reject_always`); nếu không có option phù hợp → trả `{"outcome": {"outcome": "cancelled"}}`.

### 3.4. `handlers.py` — `ClientRequestHandlers`
Thực thi request agent gọi về client, **luôn qua guard**:

| Method | Xử lý |
|--------|-------|
| `fs/read_text_file` `{sessionId, path, line?, limit?}` | guard.check_read → đọc UTF-8 (errors=replace), cắt theo line/limit → `{"content": ...}` |
| `fs/write_text_file` `{sessionId, path, content}` | guard.check_write → đọc nội dung cũ (nếu có) → ghi → phát event `file_edit` với `metadata={path, old_text, new_text, unified_diff}` |
| `terminal/create` `{command, args?, env?, cwd?, outputByteLimit?}` | guard.check_command; `cwd` phải trong workspace; spawn subprocess (Windows: `create_subprocess_exec` nếu có args, nếu là chuỗi shell thì `cmd /c`); lưu buffer output (giới hạn byte); trả `{"terminalId"}` |
| `terminal/output` | `{output, truncated, exitStatus?}` |
| `terminal/wait_for_exit` | chờ process → `{exitCode, signal}`; phát event `terminal_output` với `metadata={command, exit_code}` |
| `terminal/kill`, `terminal/release` | kill / dọn dẹp |

Bị guard deny → trả JSON-RPC error `{code: -32001, message: "Permission denied: <reason>"}` và phát event `permission` (allowed=false).

### 3.5. `client.py` — `ACPSession`
```python
class ACPSession:
    def __init__(self, cfg: AgentRuntimeConfig, workspace: Path, bin_resolver: Callable[[RuntimeType], list[str]]): ...
    async def start(self) -> None                 # spawn + initialize + session/new (+ set model nếu hỗ trợ)
    async def prompt(self, text: str) -> AsyncIterator[ACPStreamEvent]   # yield sự kiện, event cuối 'completed' kèm PromptResult trong metadata
    async def cancel(self) -> None                # notify session/cancel
    async def close(self) -> None                 # terminate → wait(5s) → kill; dọn terminals
    @property
    def alive(self) -> bool
```
Chi tiết:
- Spawn: `asyncio.create_subprocess_exec(*cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=workspace, env=merged_env, limit=16*1024*1024)`. Trên Windows `cmd` resolve qua `shutil.which` (`claude-agent-acp.cmd`).
- Task đọc stderr → logger (không gửi lên UI trừ khi process chết).
- `session/new` params: `{"cwd": str(workspace), "mcpServers": []}` + system prompt theo cách spike đã xác nhận:
  - claude-code: `"_meta": {"systemPrompt": {"append": cfg.system_prompt}}`.
  - codex: theo spike; fallback = prepend `"[SYSTEM ROLE]\n{system_prompt}\n\n"` vào prompt đầu tiên của session.
- Model: áp dụng theo spike (method set model / `_meta` / env). Nếu không set được → log warning, tiếp tục với model mặc định và gắn `metadata.model_effective`.
- `prompt()`:
  - Dùng một `asyncio.Queue[ACPStreamEvent]`; `on_notification("session/update")` map `update.sessionUpdate`:
    - `agent_message_chunk` → `message_chunk` (content.text)
    - `agent_thought_chunk` → `thought_chunk`
    - `tool_call` → `tool_call` (metadata: toolCallId, title, kind, status, locations)
    - `tool_call_update` → `tool_call_update`; nếu `content` có phần tử `type=diff` → thêm event `file_edit` (path, oldText, newText)
    - `plan` → `plan`
    - loại khác → bỏ qua (log debug)
  - Gửi `session/prompt` dạng task; khi response về → put `completed` (metadata = PromptResult) → kết thúc generator.
  - Timeout `ACP_PROMPT_TIMEOUT_SEC` → `cancel()` → event `error`.
  - Process chết giữa chừng → event `error` (kèm 50 dòng stderr cuối).
- Mỗi `ACPSession` giữ `modified_files: set[str]` (từ fs write + diff + tool_call kind=edit locations).

### 3.6. `pool.py` — `ACPProcessPool`
- Key: `(ticket_id, agent_id)` → 1 session/agent/ticket để agent nhớ ngữ cảnh khi luồng quay lại (VD tester fail → developer sửa tiếp).
- `get_or_start(cfg, workspace, ticket_id)`, `close_ticket(ticket_id)`, `close_all()` (gọi ở shutdown FastAPI).
- Idle timeout 30 phút → đóng process.
- Giới hạn tổng process đồng thời (`MAX_ACP_PROCESSES=6`), vượt → chờ.
- **`restart_agent(agent_id)`** — gọi khi cấu hình agent bị sửa (Phase 2 §6.2): với mọi session có `agent_id` đó: (1) nếu đang có `session/prompt` chạy → `session/cancel` rồi đánh dấu `turn_interrupted` (engine sẽ chạy lại **từ đầu node đó** với session mới, tối đa 1 lần, không tính vào `MAX_NODE_ITERATIONS`); (2) `session.close()` (terminate → wait 5s → kill, dọn terminal); (3) xoá khỏi pool — lần `get_or_start` kế tiếp spawn process mới với `AgentConfig` mới (runtime/model/system_prompt/permission_profile đọc lại từ DB, `DynamicPermissionGuard` dựng lại từ profile mới). Session cũ **mất ngữ cảnh hội thoại**; prompt lượt đầu của session mới là prompt “lượt đầu” đầy đủ (Phase 3 §5). Phát event `agent_restarted {agent_id, config_version}` lên EventBus (kênh user + kênh các ticket bị ảnh hưởng, kèm dòng log hệ thống `↻ @handle khởi động lại với cấu hình mới`).
- Mỗi session lưu `config_version` lúc spawn; `get_or_start` thấy `agent.config_version` lớn hơn → tự restart (an toàn kể cả khi quên gọi `restart_agent`).

### 3.7. `api_session.py` — `ApiAgentSession` (runtime `openai-api`, không dùng subprocess ACP)
Cùng interface với `ACPSession` để engine/pool không phân biệt: `async prompt(text) -> AsyncIterator[AgentEvent]`, `cancel()`, `close()`, thuộc tính `modified_files` (luôn rỗng), `config_version`. `RuntimeType` mở rộng: `claude-code | codex | openai-api`; `AgentRuntimeConfig` thêm `base_url`, `api_key` (đã giải mã trong RAM, không log), `api_params {temperature?, max_tokens?, extra_headers?}`. Pool dùng factory `create_session(cfg)` chọn lớp theo runtime.
- **Gọi API**: `httpx.AsyncClient(timeout, follow_redirects=False)` → `POST {base_url}/chat/completions` với `{model, messages, stream: true, stream_options:{include_usage:true}, ...api_params}`, header `Authorization: Bearer <key>` (+ `extra_headers`). `base_url` chuẩn hoá bỏ `/` cuối; hỗ trợ Azure (`?api-version` trong base_url / header `api-key` qua `extra_headers`).
- **Hội thoại**: `messages = [system(agent.system_prompt), ...history]`; history giữ **trong RAM theo (ticket, agent)** (giống “agent nhớ ngữ cảnh” của session ACP), cắt theo ngân sách token (`API_MAX_CONTEXT_CHARS`, giữ system + các lượt gần nhất). Khởi động lại agent / đóng ticket → xoá history.
- **Stream → AgentEvent**: SSE `data:` → `choices[0].delta.content` ⇒ `message_chunk`; `delta.reasoning_content` (nếu server có) ⇒ `thought_chunk`; chunk cuối `usage` ⇒ dòng log `tokens: prompt N · completion M`; `finish_reason` ⇒ `✔ finish_reason=stop` (hoặc `length` ⇒ cảnh báo vàng “bị cắt do max_tokens”). Phát thêm event hệ thống `→ POST <host>/chat/completions (<model>, stream)` để hiện trong log chat.
- **Không có công cụ**: không gửi `tools`; không có `fs/*`, `terminal/*`, `session/request_permission`; `DynamicPermissionGuard` không áp dụng (không có hành động nào để chặn) — thay bằng **ràng buộc cấu hình** lúc lưu agent (Phase 2 §3.2): `allow_write=false`, `allow_terminal=false`, `can_git_release=false`.
- **Lỗi**: 401/403 ⇒ `error` “API key sai hoặc không có quyền”; 404 ⇒ “Model/URL không tồn tại”; 429/5xx/timeouts ⇒ retry theo `engine/retry.py` (Phase 7 §3); mọi message lỗi **scrub** key/Authorization trước khi log; nội dung body lỗi cắt ≤ 500 ký tự.
- **Chống SSRF & rò rỉ** (kiểm tra ở service lưu agent và lúc gọi): chỉ `https://` (cho phép `http://` với host trong `API_ALLOWED_HTTP_HOSTS`, mặc định `localhost,127.0.0.1` để dùng Ollama/vLLM local); chặn IP link-local/metadata (`169.254.0.0/16`, `fd00:ec2::254`) và dải private/loopback **trừ** host nằm trong `API_ALLOWED_PRIVATE_HOSTS`; resolve DNS rồi kiểm tra IP đích (chống DNS rebinding); không follow redirect; không gửi key tới host khác với `base_url`.
- Đồng thời tối đa `MAX_API_CONCURRENCY=8` (tách khỏi `MAX_ACP_PROCESSES`); `close()` huỷ request đang chạy (`cancel` = đóng stream).

## 4. Test

### 4.1. `fake_agent.py`
Script Python đóng vai ACP agent: đọc kịch bản (list bước) từ file JSON/NDJSON trong `tests/fixtures/acp/`, ví dụ:
```json
[
 {"expect":"initialize","reply":{"protocolVersion":1,"agentCapabilities":{}}},
 {"expect":"session/new","reply":{"sessionId":"s1"}},
 {"expect":"session/prompt","then":[
    {"notify":"session/update","params":{"sessionId":"s1","update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"Đang sửa..."}}}},
    {"request":"session/request_permission","params":{"sessionId":"s1","toolCall":{"toolCallId":"t1","kind":"execute","title":"git commit","rawInput":{"command":"git commit -m x"}},"options":[{"optionId":"a1","name":"Allow","kind":"allow_once"},{"optionId":"r1","name":"Reject","kind":"reject_once"}]}, "assert_option":"r1"},
    {"request":"fs/write_text_file","params":{"sessionId":"s1","path":"{WS}/src/a.ts","content":"x"}}
 ],"reply":{"stopReason":"end_turn"}}
]
```
`bin_resolver` trong test trả `[sys.executable, "tests/acp/fake_agent.py", "<scenario>"]`.

### 4.1b. Fake OpenAI server (`tests/fakes/fake_openai.py`)
App FastAPI nhỏ giả `/v1/chat/completions` (SSE: chunk nội dung, `usage`, `finish_reason`), `/v1/models`; kịch bản `401`, `404`, `429`+`Retry-After`, `500`, treo (timeout), trả marker `@@ROUTE: ready`.

### 4.2. Test cases bắt buộc
| Test | Kỳ vọng |
|------|--------|
| `test_guard.py::test_ba_cannot_write` | profile BA → `check_write` deny |
| `test_guard.py::test_dev_git_commit_variants` | `git commit -m x`, `git  commit`, `npm test && git commit -am x`, `git -c user.name=a commit`, `GIT COMMIT` → đều deny |
| `test_guard.py::test_dev_allowed` | `npm run build`, `git status`, `git diff` → allow |
| `test_guard.py::test_path_escape` | `../outside.txt`, `C:\Windows\x`, symlink ra ngoài → deny |
| `test_guard.py::test_env_file_blocked` | đọc `.env` → deny |
| `test_guard.py::test_pick_option` | chọn đúng `allow_once` / `reject_once`; không có option → cancelled |
| `test_jsonrpc.py` | dòng rác không làm crash; request/response khớp id; EOF reject future |
| `test_handlers.py` | write sinh event `file_edit` có unified diff; terminal output bị cắt theo byte limit |
| `test_client_fake.py::test_full_turn` | stream đủ event theo kịch bản, `completed` có `modified_files` đúng |
| `test_client_fake.py::test_developer_commit_blocked` | fake agent nhận `reject` optionId (assert trong fake) + event `permission` allowed=false |
| `test_client_fake.py::test_timeout_cancel` | quá timeout → gửi `session/cancel`, event `error` |
| `test_client_real.py` (marker `real_acp`) | Claude/Codex thật: hỏi cấu trúc thư mục → có `message_chunk` + `completed` |
| `test_api_session.py::test_stream` | fake OpenAI trả SSE → `message_chunk` đủ, có dòng `tokens`, `✔ finish_reason=stop`; `modified_files` rỗng |
| `test_api_session.py::test_errors` | 401/404/429/500/timeout → event `error` đúng thông điệp; log **không** chứa API key |
| `test_api_session.py::test_ssrf` | `base_url` = `http://169.254.169.254/`, `file://`, host resolve ra IP private, redirect 302 sang nội bộ → bị chặn; `http://localhost:11434/v1` chỉ qua khi nằm trong allowlist |
| `test_pool.py::test_restart_api_agent` | `restart_agent` xoá history RAM, lượt sau là prompt “lượt đầu” |

## 5. Definition of Done

Trạng thái triển khai và bằng chứng kiểm thử: [PHASE_1_IMPLEMENTATION_NOTES.md](PHASE_1_IMPLEMENTATION_NOTES.md).
DoD chưa hoàn tất: cần xác minh Claude/API thật và cơ chế kiểm soát công cụ native.
- [ ] Tất cả test (trừ `real_acp`) pass trên Windows và Linux CI.
- [ ] `pytest -m real_acp` pass trên máy dev có CLI đã login (chạy trên thư mục sandbox copy).
- [x] Không có chỗ nào hard-code tên 4 role trong `app/acp/` — mọi quyết định dựa trên `PermissionProfile`.
- [x] Log mọi quyết định guard (agent, action, allowed, reason) ở mức INFO.
- [ ] Agent `openai-api` chạy được với fake OpenAI server và với một endpoint tương thích thật (OpenAI/OpenRouter/Ollama); không rò API key; chặn SSRF.
