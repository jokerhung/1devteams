# PHASE 0 — Khởi tạo Monorepo & Spike xác minh ACP

## 1. Mục tiêu
- Dựng khung dự án backend + frontend chạy được (hello world), tooling, lint, test.
- **Xác minh thực tế** các adapter ACP trên máy Windows đích trước khi viết code thật: tên package, cách spawn, protocol version, các message thực tế, cách chọn model. Kết quả spike ghi vào `docs/specs/ACP_SPIKE_NOTES.md` và là nguồn sự thật cho Phase 1.

## 2. Phạm vi
| Có | Không |
|----|-------|
| Cấu trúc thư mục, pyproject, Next.js init, script dev | Business logic |
| Spike script gọi ACP thật, ghi log NDJSON | UI thật |
| File `.env.example`, `config.py` | DB schema |

## 3. Công việc chi tiết

### 3.1. Backend skeleton
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings sqlalchemy[asyncio] aiosqlite asyncpg alembic \
            langgraph langgraph-checkpoint-sqlite python-jose[cryptography] passlib[bcrypt] pyyaml
pip install -D pytest pytest-asyncio httpx ruff mypy
```
- `pyproject.toml`: ruff (line 110), mypy strict cho `app/acp` và `app/engine`, pytest `asyncio_mode = "auto"`.
- `app/core/config.py` (pydantic-settings):

| Biến | Mặc định | Ý nghĩa |
|------|----------|--------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./aiteams.db` | |
| `CHECKPOINT_DB` | `./checkpoints.db` | LangGraph checkpointer |
| `JWT_SECRET` | (bắt buộc) | |
| `CLAUDE_ACP_BIN` | `claude-agent-acp` | tên/đường dẫn binary |
| `CODEX_ACP_BIN` | `codex-acp` | |
| `ALLOWED_WORKSPACE_ROOTS` | `D:\VETC` | danh sách gốc được phép làm workspace (phân cách `;`) |
| `ACP_PROMPT_TIMEOUT_SEC` | `1800` | timeout một lượt agent |
| `CORS_ORIGINS` | `http://localhost:3000` | |

- `app/main.py`: FastAPI app, `GET /api/health` → `{"status":"ok","acp":{"claude":bool,"codex":bool}}` (kiểm tra `shutil.which`).
- **Windows**: ở đầu `main.py` (và trong `tests/conftest.py`):
  ```python
  import sys, asyncio
  if sys.platform == "win32":
      asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
  ```
  Chạy dev bằng `uvicorn app.main:app --port 8000` (không `--reload`) hoặc `--reload` kèm `--loop asyncio` sau khi đã xác nhận policy hoạt động.

### 3.2. Frontend skeleton
```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir
cd frontend
npx shadcn@latest init
npx shadcn@latest add button input textarea label select badge tabs switch dialog dropdown-menu scroll-area sonner tooltip separator checkbox avatar
npm i @tanstack/react-query zustand lucide-react @xyflow/react react-markdown remark-gfm
```
- `src/lib/api.ts`: fetch wrapper, base `NEXT_PUBLIC_API_URL=http://localhost:8000`.
- Trang `/` gọi `/api/health` hiển thị trạng thái “ACP Connected” (giống góc sidebar trong mockup).

### 3.3. Spike ACP (bắt buộc làm trên máy Windows có workspace thật)
1. Cài adapter. **Xác minh tên package thực tế trên npm** (PDF ghi `@agentclientprotocol/claude-agent-acp`, `@agentclientprotocol/codex-acp`; các tên từng tồn tại khác: `@zed-industries/claude-code-acp`, `@zed-industries/claude-agent-acp`, `@zed-industries/codex-acp`). Ghi lại tên + version đã dùng.
2. Đảm bảo CLI đã login: `claude` (đăng nhập Claude Pro/Max) và `codex login`.
3. Viết `backend/scripts/acp_spike.py`:
   - Spawn binary (`shutil.which` để lấy `.cmd` trên Windows), `cwd` = thư mục test (copy nhỏ của repo, KHÔNG dùng repo thật).
   - Gửi `initialize`:
     ```json
     {"jsonrpc":"2.0","id":1,"method":"initialize","params":{
       "protocolVersion":1,
       "clientCapabilities":{"fs":{"readTextFile":true,"writeTextFile":true},"terminal":true},
       "clientInfo":{"name":"aiteams","version":"0.1.0"}}}
     ```
   - Gửi `session/new` `{"cwd": "<abs path>", "mcpServers": []}` → lấy `sessionId`, **ghi lại toàn bộ response** (đặc biệt các field `models`, `modes` nếu có).
   - Gửi `session/prompt` `{"sessionId": "...", "prompt":[{"type":"text","text":"Liệt kê các file trong thư mục src và tạo file hello.txt"}]}`.
   - Log **từng dòng** stdout vào `spike_logs/<runtime>_<timestamp>.ndjson`, stderr riêng.
   - Với mọi request từ agent (`session/request_permission`, `fs/*`, `terminal/*`): in ra, trả lời tối thiểu để luồng chạy tiếp (permission chọn option `kind=allow_once`; fs đọc/ghi file thật trong thư mục test; terminal chạy bằng subprocess).
4. Thử truyền system prompt:
   - Claude: `session/new` params `_meta: {"systemPrompt": {"append": "Bạn là BA..."}}` (cơ chế ClaudeMeta mà Buzz dùng) — kiểm tra có hiệu lực không (hỏi “vai trò của bạn là gì”).
   - Codex: kiểm tra cách adapter nhận system prompt (field/`_meta`/ghép vào prompt đầu). Nếu không có kênh riêng → phương án dự phòng: **prepend** system prompt vào prompt đầu tiên của session.
5. Thử chọn model: kiểm tra adapter có hỗ trợ `session/set_model` (hoặc tương đương, có thể là unstable) / `_meta` / biến môi trường (`ANTHROPIC_MODEL` cho Claude Code, `-c model=...`/config cho Codex). Ghi lại cách hoạt động.
6. Thử `session/cancel` (notification) giữa chừng.
7. Ghi kết quả vào `docs/specs/ACP_SPIKE_NOTES.md` theo mẫu:

```markdown
| Hạng mục | claude-agent-acp | codex-acp |
|---|---|---|
| Package & version | | |
| protocolVersion trả về | | |
| agentCapabilities | | |
| session/new trả về models? | | |
| Cách set system prompt | | |
| Cách set model | | |
| Các sessionUpdate quan sát được | | |
| Agent có gọi fs/* của client không, hay tự ghi file? | | |
| Agent có gọi terminal/* không, hay tự chạy Bash? | | |
| Dạng params của request_permission (toolCall.kind, rawInput) | | |
```

> ⚠️ Điểm then chốt cần trả lời: nếu adapter **tự** ghi file/chạy bash (không qua `fs/*`, `terminal/*` của client), thì lớp enforce duy nhất là `session/request_permission` → Phase 1 phải đảm bảo mọi tool ghi/thực thi đều đi qua request_permission (hoặc cấu hình mode của adapter để luôn hỏi quyền).

### 3.4. Scripts
- `scripts/dev.ps1`: chạy backend (port 8000) + frontend (port 3000) song song.
- `.gitignore`: `.venv`, `node_modules`, `*.db`, `spike_logs/`, `.env`.

## 4. Definition of Done
- [ ] `GET /api/health` trả 200, hiển thị đúng trạng thái 2 binary.
- [ ] `npm run dev` hiển thị trang health.
- [ ] `ruff`, `mypy`, `pytest` (1 test health) chạy pass.
- [ ] `ACP_SPIKE_NOTES.md` điền đủ bảng, kèm 2 file log NDJSON mẫu (đã xóa thông tin nhạy cảm) đặt trong `backend/tests/fixtures/acp/` để Phase 1 dùng làm dữ liệu test giả lập.
