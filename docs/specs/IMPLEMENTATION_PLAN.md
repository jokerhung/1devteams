# aiTeams — MASTER IMPLEMENTATION PLAN

> Nền tảng điều phối đội AI Agent (BA / Developer / Tester / Leader + Custom Agent) làm việc trực tiếp trên thư mục mã nguồn local, giao tiếp với **Claude Code** và **OpenAI Codex** qua **ACP (Agent Client Protocol)**, workflow kéo thả kiểu **Dify**, giao diện phòng chat kiểu **Buzz** (bản tối giản — xem `docs/aiTeams_gui.html`).
>
> Nguồn: `docs/chat thiet ke aiTeams.pdf` (toàn bộ trao đổi thiết kế) + `docs/aiTeams_gui.html` (mockup giao diện chốt).

---

> **Cập nhật thiết kế v2 (22/10/2026):** AI Team gồm ≥ 1 agent; 1 Project có ≥ 1 Workflow; 1 Workflow có ≥ 0..n Ticket (ticket thuộc về đúng 1 workflow); thứ tự tạo **Project → Workflow → Ticket → mở cửa sổ chat**. Bỏ khái niệm “workflow active của project”.

> **Cập nhật đồng bộ giao diện v2.1 (22/10/2026)** — theo mockup `docs/aiTeams_gui.html` đã chốt:
> 1. **Sidebar**: bỏ ô tìm kiếm, bỏ tab “Tổng quan & Workflows” và mục “Agent trong project”; “Hộp thư” → **Thông báo** (chỉ lưu việc cần người dùng tương tác); AI Agents + AI Teams gộp thành **một trang “Agents & Teams”**; hiển thị **5 project gần nhất** (thứ tự ổn định theo `last_activity_at`, project hiện tại được ghim ô 5), click **tên** project → tổng quan, **chevron riêng** để thu gọn/mở rộng từng project (không tự collapse).
> 2. **Tạo project chỉ tạo project trống** (tên, đường dẫn, nhánh); AI Team, workflow, ticket tạo sau từng bước.
> 3. **Agent/Team**: có **logo** (24 emoji hoặc ảnh ≤ 300KB); **sửa được agent và team**; **mỗi lần sửa agent ⇒ khởi động lại agent** (cảnh báo trước, trạng thái “Đang khởi động lại…”).
> 4. **Chat**: nút **@ popup** chọn agent và **nhớ làm mặc định** cho các chat sau; **đính kèm file** (📎 bên phải nút @, kéo thả, dán ảnh; ≤ 5 file, ≤ 10MB); **log ACP gắn vào từng dòng chat** của agent (hiện dòng cuối + mũi tên xổ toàn bộ; “Xem toàn bộ log” có lọc/copy).
> Chi tiết: Phase 2 (DB/API), Phase 3 (engine), Phase 4 (shell), Phase 6 (chat).

## 1. Mục tiêu sản phẩm

| # | Tính năng | Mô tả ngắn |
|---|-----------|-----------|
| F1 | **Agent** | Tạo/sửa/xóa agent: handle `@name`, vai trò, mô tả chi tiết (system prompt), runtime `claude-code` \| `codex` \| **`openai-api`** (gọi ChatGPT/OpenAI-compatible API với **Base URL tuỳ chỉnh** + API key), model, permission profile. 4 agent mặc định `@ba`, `@developer`, `@tester`, `@leader` (built-in, không xóa được). |
| F2 | **AI Team** | Một AI Team gồm **một hoặc nhiều** AI Agent (bắt buộc ≥ 1). VD: *Core Bugfix Squad* = @ba, @developer, @tester, @leader. Agent và team đều có **logo** và **sửa được** (sửa agent ⇒ khởi động lại agent). Quản lý trong một trang **Agents & Teams**. |
| F3 | **Project** | Trỏ tới thư mục local (VD: `D:\VETC\FE\HNBG_DEV`), nhánh git; thêm **member** (user), thêm **agent lẻ** hoặc **AI Team**. Một project có **một hoặc nhiều Workflow**. |
| F4 | **Workflow** | Thuộc 1 project, thiết kế bằng **kéo thả**; mỗi workflow là một “quy trình” riêng (VD *Fix Bug*, *Làm tính năng*, *Review bảo mật*), có prefix mã ticket riêng (`BUG`, `FEAT`…). Một workflow chứa **nhiều ticket**. |
| F5 | **Ticket** | Tạo ticket **bên trong một workflow** → hệ thống **mở ngay cửa sổ chat** (mỗi ticket = 1 channel `# bug-...`) và chạy theo workflow đó; Human-in-the-loop: BA hỏi lại user, user xác nhận trước khi Leader commit & push. |
| F7 | **Thông báo** | Lưu các sự kiện **cần người dùng tương tác** (xác nhận trước khi push, agent hỏi lại): tab *Cần xử lý* / *Đã xử lý*, badge ở sidebar, tự resolve khi người dùng xử lý. Thay cho “Hộp thư”. |
| F8 | **Tiện ích chat** | Nút @ chọn agent mặc định (nhớ cho mọi chat), đính kèm file/ảnh, log ACP gắn từng lượt trả lời của agent (dòng cuối + mở rộng). |
| F6 | **Luật Git** | Chỉ `@leader` được commit/push, và chỉ sau khi user xác nhận. Developer/Tester tuyệt đối không commit/push. |

### 1.1. Mô hình nghiệp vụ & thứ tự tạo

```text
AI Agent ──(n..n)── AI Team (≥1 agent)
                        │ thêm vào project (cùng user, agent lẻ)
                        ▼
Project (workspace_path) ──1..n──► Workflow (graph kéo thả, prefix) ──0..n──► Ticket ──1──► Channel chat (ticket_messages)
```

Luồng người dùng bắt buộc:
1. **Tạo Project trống** (chỉ tên, đường dẫn thư mục, nhánh) → rồi mới **thêm member / agent / AI Team** ở “Thành viên & AI Team”.
2. **Tạo Workflow** trong project (từ trống hoặc template) → thiết kế → **Xuất bản** (graph hợp lệ). Project chưa có workflow nào → UI dẫn thẳng sang bước tạo workflow.
3. **Tạo Ticket** trong một workflow đã xuất bản (nhập tiêu đề + mô tả).
4. **Cửa sổ chat của ticket mở ra ngay** và workflow tự bắt đầu chạy (`@ba` nhận việc đầu tiên).

## 2. Quyết định kiến trúc (chốt từ tài liệu thiết kế)

| Tầng | Công nghệ | Ghi chú |
|------|-----------|--------|
| Agent runtime | `claude-agent-acp` (Claude Code), `codex-acp` (Codex) — chạy subprocess, JSON-RPC 2.0 qua stdio | Dùng phiên đăng nhập sẵn của CLI (Claude Pro/Max, ChatGPT Plus/Pro) → không bắt buộc API key |
| Agent runtime #3 | **`openai-api`** — HTTP streaming tới endpoint tương thích OpenAI (`POST {base_url}/chat/completions`), Base URL tuỳ chỉnh (OpenAI, Azure OpenAI, OpenRouter, LiteLLM, Ollama, vLLM…) | **Chỉ trả lời văn bản (text-only)**: không có công cụ đọc/sửa file hay chạy lệnh; không có subprocess ACP. API key lưu mã hoá ở backend. Xem Phase 1 §3.7 |
| Backend | Python 3.11+, FastAPI, asyncio | |
| Orchestration | LangGraph (StateGraph + `interrupt()` + checkpointer) | Biên dịch động từ JSON React Flow |
| DB | SQLite (dev) / PostgreSQL (prod), SQLAlchemy 2 async + Alembic | |
| Realtime | WebSocket (FastAPI) + in-process EventBus (Redis Pub/Sub là tùy chọn khi scale) | |
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui | Style Buzz-minimal theo `aiTeams_gui.html` |
| Workflow canvas | `@xyflow/react` | |
| Terminal từ xa | PTY (`pywinpty` trên Windows / `ptyprocess` trên Linux) + `@xterm/xterm` | Phase 7 |

### 2.1. Các điều chỉnh so với bản nháp trong PDF (quan trọng)

1. **Giao thức ACP phải bám theo spec thật**, không theo payload phỏng đoán trong PDF:
   - `initialize` → `protocolVersion` là **số nguyên** (hiện tại `1`), field là `clientCapabilities` (không phải `capabilities`).
   - `session/new` nhận `{cwd, mcpServers: []}` và trả về `sessionId`; mọi `session/prompt` phải kèm `sessionId`.
   - Xin quyền là method **`session/request_permission`** (snake_case), response `{"outcome": {"outcome": "selected", "optionId": "<id lấy từ params.options>"}}` — **optionId phải lấy từ danh sách `options` agent gửi** (kind `allow_once`/`reject_once`...), không hard-code `"allow"`/`"deny"`.
   - Agent → Client còn gọi `fs/read_text_file`, `fs/write_text_file`, `terminal/create`, `terminal/output`, `terminal/wait_for_exit`, `terminal/kill`, `terminal/release` → backend phải **tự thực thi** các request này (và đây là chỗ thứ 2 để enforce quyền).
   - Phase 0 có bước **spike** xác minh tên package npm, version protocol, cách set model với bản adapter đang cài.
2. **Phòng thủ nhiều lớp cho luật Git**: (a) guard ở `session/request_permission`, (b) guard ở handler `terminal/create` & `fs/write_text_file` (chặn path ngoài workspace, chặn lệnh cấm), (c) **thao tác git commit/push của Leader do backend thực thi bằng `GitService` tất định** — LLM Leader chỉ review diff và đề xuất commit message dạng JSON. Không bao giờ để LLM tự gõ `git push`.
3. **Một ticket đang chạy / một workspace** (workspace lock) vì các agent cùng sửa một working directory.
4. **Danh sách model không hard-code** tên cũ (`claude-3-x`, `gpt-4o` trong PDF đã lỗi thời): lấy từ cấu hình `models_catalog.yaml` + danh sách model adapter trả về khi tạo session (nếu có).
6. **Agent loại `openai-api` là “agent chỉ trả lời văn bản”** (v1): không có fs/terminal nên engine **chủ động đưa ngữ cảnh vào prompt** (STR, output các agent trước, `git diff` của các file đã sửa, đoạn file liên quan — có giới hạn kích thước) thay vì để agent tự đọc. Vì vậy loại này phù hợp vai trò **BA, review/bảo mật, tóm tắt, giải thích**; **không** dùng cho `@developer`/`@tester` (cần sửa file/chạy test) và **không** làm node `git_release` ở v1. Validator và form tạo agent chặn các nhóm quyền ghi/chạy lệnh cho loại này.
5. **Windows**: backend chạy trên máy có workspace `D:\...` → bắt buộc dùng ProactorEventLoop (mặc định), **không dùng `uvicorn --reload`** khi test subprocess (reload dùng SelectorEventLoop → `NotImplementedError`), resolve binary bằng `shutil.which()` (npm global trên Windows là file `.cmd`).

## 3. Cấu trúc monorepo

```text
aiTeams/
├── docs/
│   ├── aiTeams_gui.html
│   ├── chat thiet ke aiTeams.pdf
│   └── specs/
│       ├── IMPLEMENTATION_PLAN.md          ← file này
│       ├── PHASE_0_SETUP_AND_SPIKE.md
│       ├── PHASE_1_ACP_BRIDGE.md
│       ├── PHASE_2_DB_AND_API.md
│       ├── PHASE_3_WORKFLOW_ENGINE.md
│       ├── PHASE_4_FRONTEND_SHELL_AND_MANAGEMENT.md
│       ├── PHASE_5_WORKFLOW_BUILDER.md
│       ├── PHASE_6_TICKET_CHAT_RUNTIME.md
│       └── PHASE_7_TERMINAL_HARDENING.md
├── backend/
│   ├── app/
│   │   ├── core/        (config.py, logging.py, security.py, events.py)
│   │   ├── acp/         (types.py, jsonrpc.py, guard.py, handlers.py, client.py, pool.py)
│   │   ├── db/          (base.py, session.py, models.py)
│   │   ├── schemas/     (agent.py, team.py, project.py, workflow.py, ticket.py, user.py)
│   │   ├── services/    (agent_service.py, project_service.py, git_service.py, seed.py, models_catalog.py)
│   │   ├── engine/      (state.py, prompts.py, markers.py, nodes.py, compiler.py, runner.py)
│   │   ├── api/         (auth.py, agents.py, teams.py, projects.py, workflows.py, tickets.py, notifications.py, assets.py, preferences.py)
│   │   ├── ws/          (manager.py, ticket_ws.py, terminal_ws.py)
│   │   └── main.py
│   ├── alembic/
│   ├── config/models_catalog.yaml
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── app/ (login, notifications, agents[=Agents & Teams; /teams redirect], projects/[id]/{page,members,settings,
│       │         workflows/{page,[wid]/{page,edit,tickets/[ticketId]}}})
│       ├── components/ (layout, agents, teams, projects, workflow, ticket-chat, ui)
│       ├── lib/ (api.ts, ws.ts, types.ts, query-keys.ts)
│       └── stores/ (ticket-store.ts)
└── scripts/ (dev.ps1, dev.sh)
```

## 4. Hợp đồng dữ liệu dùng chung (tham chiếu xuyên phase)

### 4.1. `AgentEvent` — sự kiện chuẩn hóa từ ACP → DB → WebSocket

```jsonc
{
  "id": "uuid",
  "ticket_id": "uuid",
  "run_id": "uuid",
  "node_id": "n_dev",              // node trong workflow
  "sender_type": "AGENT",          // USER | AGENT | SYSTEM
  "sender_name": "@developer",
  "event_type": "message_chunk",   // xem bảng 4.2
  "content": "text...",
  "metadata": { },                 // path, diff, command, exit_code, tool_call_id, model...
  "created_at": "2026-10-22T09:18:00Z"
}
```

### 4.2. `event_type`

| event_type | Nguồn ACP | Hiển thị UI |
|-----------|-----------|-------------|
| `message_chunk` | `session/update` → `agent_message_chunk` | Gộp thành nội dung tin nhắn markdown |
| `thought_chunk` | `agent_thought_chunk` | Khối “Thinking” thu gọn |
| `tool_call` / `tool_call_update` | `tool_call`, `tool_call_update` | Badge “Đã đọc file…”, “Chạy lệnh…”; đồng thời là **dòng log agent** (dòng cuối + mũi tên mở rộng gắn vào từng lượt chat) |
| `file_edit` | `fs/write_text_file` hoặc tool_call kind=`edit` có diff | `<details>` “Xem thay đổi mã nguồn” |
| `terminal_output` | `terminal/*` | Khối terminal đen |
| `permission` | `session/request_permission` + quyết định guard | Log nhỏ (ALLOW/DENY) |
| `plan` | `plan` | Checklist kế hoạch |
| `agent_turn_start` / `agent_turn_end` | Engine | Tạo/đóng “bong bóng” của agent |
| `gate_waiting` | Engine (`interrupt`) | Ô xác nhận / ô trả lời BA; đồng thời tạo **thông báo** |
| `notification_created` / `notification_resolved` | Engine → kênh `/ws/users/me` | Badge + danh sách trang Thông báo |
| `agent_restarted` | Pool (sau khi sửa cấu hình agent) | Badge “Đang khởi động lại…” → toast hoàn tất; dòng log `↻` trong chat |
| `ticket_status` | Engine | Badge trạng thái channel + footer status |
| `error` | Bất kỳ | Thông báo đỏ |

### 4.3. Trạng thái ticket

`OPEN → RUNNING → (WAITING_USER_INPUT ⇄ RUNNING) → WAITING_USER_CONFIRM → RUNNING(leader) → COMPLETED`; nhánh lỗi: `FAILED`, `CANCELLED`.

### 4.4. Permission profile

```json
{ "allow_read": true, "allow_write": false, "allow_terminal": false,
  "allowed_commands": [], "blocked_commands": ["git commit", "git push", "git reset --hard", "rm -rf"],
  "can_git_release": false }
```

| Agent | read | write | terminal | blocked | can_git_release |
|------|------|-------|----------|---------|-----------------|
| `@ba` | ✔ | ✘ | ✘ | mặc định | ✘ |
| `@developer` | ✔ | ✔ | ✔ | mặc định | ✘ |
| `@tester` | ✔ | ✘ | ✔ (test runner) | mặc định | ✘ |
| `@leader` | ✔ | ✘ | ✔ (chỉ `git status/diff/log`) | `rm -rf`, `git push --force`, `git reset --hard` | ✔ (qua `GitService`) |

## 5. Lộ trình & phụ thuộc

| Phase | Nội dung | Phụ thuộc | Ước lượng |
|------|----------|-----------|-----------|
| 0 | Setup monorepo, spike ACP thật trên Windows | — | 2–3 ngày |
| 1 | ACP Bridge + Permission Guard + fs/terminal handlers | 0 | 4–5 ngày |
| 2 | DB + REST API (users, agents, teams, projects, members, workflows, tickets) + seed | 0 | 4–5 ngày |
| 3 | Workflow Engine (compiler LangGraph, gates, GitService, runner, WebSocket) | 1, 2 | 6–8 ngày |
| 4 | Frontend shell Buzz-minimal + quản lý Agent/Team/Project/Member | 2 | 4–5 ngày |
| 5 | Workflow Builder kéo thả (React Flow) | 4, (schema của 3) | 4–5 ngày |
| 6 | Ticket Chat Runtime (stream, gates, diff, live progress) | 3, 4 | 5–6 ngày |
| 7 | Remote terminal PTY, fallback model, cancel/retry, audit, E2E | 6 | 4–5 ngày |

Phase 2 và Phase 1 có thể làm song song; Phase 4 có thể bắt đầu ngay khi API Phase 2 ổn.

## 6. Cách giao việc cho Codex / Claude Code

Giao **từng phase một**, không nhảy phase. Prompt mẫu:

```text
Đọc docs/specs/IMPLEMENTATION_PLAN.md và docs/specs/PHASE_<N>_*.md.
Triển khai đầy đủ Phase <N> đúng cấu trúc thư mục và hợp đồng dữ liệu đã mô tả.
Viết test theo mục "Definition of Done". Chạy test và sửa đến khi pass.
Không triển khai tính năng của phase sau. Khi xong, liệt kê file đã tạo/sửa và các điểm lệch so với spec (nếu có).
```

## 7. Definition of Done toàn hệ thống (E2E)

1. Tạo project `HNBG_DEV` trỏ `D:\VETC\FE\HNBG_DEV` (**project trống**), rồi ở “Thành viên & AI Team” thêm AI Team *Core Bugfix Squad* (4 agent).
2. Tạo workflow **Fix Bug** (prefix `BUG`) từ template mặc định → Xuất bản. (Tạo thêm workflow thứ 2 *Fix Bug + Security Review* để kiểm tra 1 project nhiều workflow.)
3. Trong workflow *Fix Bug*, tạo ticket “Nút Xuất Excel bị đơ khi chọn khoảng ngày lớn” → **cửa sổ chat `# bug-xuat-excel` mở ngay**, mã `#BUG-1`, workflow tự chạy.
4. `@ba` hỏi lại 1 câu → user trả lời trong chat → `@ba` xuất STR.
5. `@developer` sửa file (diff hiển thị trong chat), cố chạy `git commit` → bị chặn và log DENY.
6. `@tester` chạy test, báo PASS → hộp xác nhận hiện trong tin nhắn tester.
7. User bấm **Xác nhận (Báo @leader Push Git)** → `@leader` review diff → backend commit + push → commit hash hiện trong chat, ticket `COMPLETED`.
8. Nhánh phụ: user bấm **Chưa đạt, sửa lại** + feedback → luồng quay về `@developer`.
9. Sidebar hiển thị 5 project gần nhất (thứ tự ổn định khi click, mỗi project có nút thu gọn riêng), cây Project → Workflow → Ticket đúng; sửa workflow *Fix Bug* (version mới) không ảnh hưởng ticket đang chạy.
10b. Tạo agent loại **OpenAI Custom** (Base URL tuỳ chỉnh + API key + model) → “Kiểm tra kết nối” OK → đưa vào một workflow (VD review bảo mật) → chạy ticket: log chat hiện `→ POST <host>/chat/completions …`, kết quả trả về dạng văn bản, API key không bao giờ hiện lại trên UI/log/API.
10. Tạo logo cho một agent tuỳ chỉnh, **sửa agent** → thấy “Đang khởi động lại…”; đang có ticket chạy dùng agent đó → lượt chạy lại từ đầu bước.
11. Ở bước 6 có thông báo “Cần xác nhận” (badge sidebar = 1); xác nhận xong thông báo chuyển sang “Đã xử lý”.
12. Trong chat: chọn `@developer` làm mặc định ở nút @ → các tin sau (kể cả ticket khác) tự gửi tới `@developer`; đính kèm ảnh + file log; mỗi lượt của agent có dòng log cuối + mũi tên mở toàn bộ log.
