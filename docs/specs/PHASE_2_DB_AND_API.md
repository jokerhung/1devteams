# PHASE 2 — Database Schema & REST API (Users, Agents, Teams, Projects, Members, Workflows, Tickets)

## 1. Mục tiêu
- Tầng lưu trữ SQLAlchemy 2 async + Alembic (SQLite dev, PostgreSQL prod — chỉ dùng kiểu `JSON` chung, không dùng `JSONB` riêng Postgres để chạy được cả hai).
- REST API FastAPI cho toàn bộ tính năng quản trị F1–F4 (chưa chạy workflow — Phase 3).
- Seed 4 agent mặc định, team mặc định, workflow mẫu.

## 2. Cấu trúc file
```text
backend/app/
├── db/ base.py, session.py, models.py   # + notifications, user_preferences, attachments
├── schemas/ user.py, agent.py, team.py, project.py, workflow.py, ticket.py, common.py
├── services/ agent_service.py, team_service.py, project_service.py, ticket_service.py,
│             seed.py, models_catalog.py, workspace_validator.py
├── core/ security.py (hash, JWT), deps.py (get_db, get_current_user)
└── api/ auth.py, users.py, agents.py, teams.py, projects.py, workflows.py, tickets.py, notifications.py, assets.py, preferences.py
backend/config/models_catalog.yaml
backend/alembic/versions/0001_init.py
backend/tests/api/ ...
```

## 3. Database models (`app/db/models.py`)

> **Thiết kế v2 — quan hệ chính:**
> `teams 1─n team_agents n─1 agents` (team ≥ 1 agent) · `projects 1─n workflows` (project ≥ 1 workflow trước khi tạo ticket) · `workflows 1─n tickets` (ticket bắt buộc có `workflow_id`) · `tickets 1─n ticket_messages`.
> Thứ tự tạo: **project → workflow → ticket → chat**.
Tất cả bảng có `id: UUID (PK, default uuid4)`, `created_at`, `updated_at`.

### 3.1. `users`
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| email | String(255) unique | |
| display_name | String(100) | VD: *Nguyen Manh Hung* |
| password_hash | String | bcrypt |
| system_role | String(20) | `OWNER` \| `ADMIN` \| `MEMBER` |
| avatar_initials | String(4) | VD `NH` (tự sinh) |

### 3.2. `agents`
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| handle | String(50) unique | regex `^@[a-z0-9_\-]{2,49}$` (lưu lowercase) |
| display_name | String(100) | VD *Business Analyst* |
| role_key | String(50) | `BA`, `DEVELOPER`, `TESTER`, `LEADER`, `SECURITY`, `DEVOPS`, `CUSTOM`… (tự do, uppercase) |
| description | Text nullable | mô tả ngắn hiển thị trên card |
| system_prompt | Text | mô tả chi tiết vai trò |
| runtime | String(20) | `claude-code` \| `codex` \| `openai-api` |
| base_url | String(300) nullable | chỉ với `openai-api`: URL gốc tương thích OpenAI, VD `https://api.openai.com/v1`, `https://openrouter.ai/api/v1`, `http://localhost:11434/v1`. Validate: `^https?://`, chống SSRF (Phase 1 §3.7) |
| api_key_enc | Text nullable | API key **mã hoá** (Fernet, khoá `APP_SECRET_KEY` trong env); **không bao giờ** trả ra API/UI/log |
| api_key_last4 | String(4) nullable | 4 ký tự cuối để hiển thị “•••• 7f2a” |
| api_params | JSON nullable | `{temperature?, max_tokens?, extra_headers?}` (header mở rộng cũng mã hoá nếu chứa secret) |
| model | String(100) nullable | null = mặc định của CLI |
| fallback_model | String(100) nullable | dùng ở Phase 7 |
| permission_profile | JSON | theo `PermissionProfile` (Phase 1) |
| icon | String(8) | emoji logo, VD 🐝 🛠️ 🧪 🚀 🤖 (24 emoji chọn sẵn ở UI) |
| logo_url | String(300) nullable | logo **ảnh tải lên** (≤ 300KB, `POST /assets/logo`); nếu có thì ưu tiên hơn `icon` |
| config_version | Integer | tăng 1 mỗi lần sửa cấu hình agent (mọi PATCH có thay đổi) — engine so sánh với version của session để biết phải khởi động lại |
| restarted_at | DateTime nullable | lần khởi động lại gần nhất |
| color | String(20) | `sky`, `amber`, `emerald`, `purple`, `stone`… |
| is_builtin | Boolean | 4 agent mặc định = True |
| is_active | Boolean | soft-disable |

### 3.3. `teams` (AI Team), `team_agents`
- `teams`: name (unique), description, icon (emoji), `logo_url` nullable (ảnh tải lên, cùng quy tắc với agent).
- `team_agents`: team_id FK (cascade), agent_id FK (restrict), `position` int (thứ tự hiển thị). PK (team_id, agent_id).
- **Ràng buộc nghiệp vụ: một AI Team phải có ít nhất 1 agent** — kiểm tra ở service khi tạo/sửa (không cho tạo team rỗng, không cho gỡ agent cuối cùng; muốn bỏ hết thì xóa team).
- Xóa/vô hiệu hóa agent đang là thành viên duy nhất của một team → 409, yêu cầu thêm agent khác vào team hoặc xóa team trước.

### 3.4. `projects`
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| name | String(100) unique | `HNBG_DEV` |
| description | Text | |
| workspace_path | String(500) | `D:\VETC\FE\HNBG_DEV` |
| default_branch | String(200) | nhánh @leader push, VD `hotfix/reconciliation` |
| git_remote | String(100) | mặc định `origin` |
| owner_id | FK users | |
| next_ticket_number | Integer | bộ đếm số ticket dùng chung cho mọi workflow của project |
| last_activity_at | DateTime | sắp xếp “5 project gần nhất” ở sidebar. Được set = now khi **tạo project** và khi **tạo ticket mới**; **không** đổi khi chỉ mở/xem project, đổi trạng thái ticket hay sửa cấu hình |

> **Project trống hợp lệ:** `POST /projects` chỉ cần `name`, `workspace_path`, `default_branch` — tạo project **không** kèm member/team/workflow. AI Team, agent lẻ, workflow, ticket được thêm sau bằng các endpoint riêng.
> Không còn `active_workflow_id`: project có nhiều workflow song song, ticket chọn workflow lúc tạo.

### 3.5. `project_members`
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| project_id | FK cascade | |
| member_type | String(10) | `USER` \| `AGENT` \| `TEAM` |
| member_id | UUID | id của user/agent/team |
| project_role | String(20) nullable | với USER: `MAINTAINER` \| `REPORTER` \| `VIEWER` |
Unique (project_id, member_type, member_id).

> **Agent hiệu lực của project** = agent thêm lẻ ∪ agent thuộc các team đã thêm (distinct). Service `project_service.effective_agents(project_id)` dùng cho Workflow Builder và Engine.

### 3.6. `workflows` (một project có nhiều workflow)
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| project_id | FK cascade | |
| name | String(100) | unique trong project. VD *Fix Bug*, *Fix Bug + Security Review*, *Làm tính năng* |
| description | Text | |
| ticket_prefix | String(10) | VD `BUG`, `FEAT`, `SEC` → mã ticket `#BUG-104`; regex `^[A-Z]{2,10}$`, unique trong project |
| icon / color | String | hiển thị trên sidebar |
| status | String(20) | `DRAFT` (chưa xuất bản) \| `PUBLISHED` \| `ARCHIVED` |
| current_version | Integer | version graph mới nhất (bản nháp đang sửa) |
| published_version | Integer nullable | version được dùng khi tạo ticket mới |
| graph | JSON | graph bản nháp hiện tại `{nodes, edges, viewport}` — schema mục 5 |
| is_valid | Boolean | kết quả validate của graph hiện tại |
| validation_errors | JSON | list lỗi |
| position | Integer | thứ tự trong sidebar |

### 3.6b. `workflow_versions` (snapshot bất biến)
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| workflow_id | FK cascade | |
| version | Integer | unique (workflow_id, version) |
| graph | JSON | bản đã xuất bản |
| published_by / published_at | | |

Quy tắc:
- Lưu graph chỉ cập nhật `workflows.graph` + `current_version += 1` (bản nháp). **Xuất bản** = validate → nếu hợp lệ ghi một dòng `workflow_versions` và đặt `published_version`, `status=PUBLISHED`.
- Chỉ workflow `PUBLISHED` (có `published_version`) mới được tạo ticket.
- Ticket lưu `workflow_version` = `published_version` tại thời điểm tạo → sửa/xuất bản lại workflow **không ảnh hưởng** ticket đã tạo.
- Không xóa cứng workflow đã có ticket → chỉ `ARCHIVED` (ẩn khỏi nút tạo ticket, ticket cũ vẫn xem được). Workflow chưa có ticket → xóa được.
- Project phải còn ít nhất 1 workflow chưa archived khi đã có ticket (chặn archive workflow cuối cùng).

### 3.7. `tickets` (thuộc về đúng 1 workflow)
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| project_id | FK | denormalize để query nhanh / khóa workspace |
| workflow_id | FK **not null** → workflows | ticket nằm trong workflow này |
| workflow_version | Integer not null | snapshot `published_version` lúc tạo |
| number | Integer | lấy từ `projects.next_ticket_number` (tăng atomic) → hiển thị `#{workflow.ticket_prefix}-{number}` |
| channel_slug | String(80) | VD `bug-xuat-excel` (`<prefix lowercase>-<slug tiêu đề>`, bỏ dấu tiếng Việt, ≤ 40 ký tự, unique trong project) |
| title | String(200) | |
| description | Text | mô tả lỗi/yêu cầu ban đầu |
| status | String(30) | `OPEN`, `RUNNING`, `WAITING_USER_INPUT`, `WAITING_USER_CONFIRM`, `COMPLETED`, `FAILED`, `CANCELLED` |
| reporter_id | FK users | |
| thread_id | String | LangGraph thread (= ticket id) |
| current_node_id | String nullable | node đang chạy |
| result | JSON | `{commit_hash, branch, files, pushed_at}` |

### 3.8. `ticket_messages`
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| ticket_id | FK cascade, index | |
| run_id | UUID nullable | 1 lượt chạy của 1 node |
| node_id | String nullable | |
| sender_type | String(10) | `USER` \| `AGENT` \| `SYSTEM` |
| sender_id | UUID nullable | user/agent id |
| sender_name | String(100) | `@developer`, `Nguyen Manh Hung` |
| event_type | String(30) | theo IMPLEMENTATION_PLAN §4.2 |
| content | Text | |
| metadata | JSON | |
| seq | BigInteger | tăng dần trong ticket — dùng để client resume WS |
Index (ticket_id, seq).

### 3.9. `attachments` (file đính kèm tin nhắn / ticket)
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| ticket_id | FK cascade, index | |
| message_id | FK `ticket_messages` nullable | null cho tới khi tin nhắn được gửi (file “chờ gửi”); file chờ > 24h chưa gắn → dọn rác |
| uploaded_by | FK users | |
| filename | String(255) | tên gốc (đã sanitize) |
| mime | String(100) | |
| size | BigInteger | byte |
| storage_path | String(500) | `data/blobs/attachments/<ticket>/<uuid>_<name>` |
| thumbnail_path | String nullable | thumbnail cho ảnh |

Giới hạn (cấu hình): `ATTACH_MAX_FILES=5` file/tin nhắn, `ATTACH_MAX_MB=10` mỗi file, chặn đuôi thực thi (`.exe .bat .cmd .ps1 .sh .msi` trừ khi bật `ATTACH_ALLOW_SCRIPTS`), kiểm tra mime bằng magic bytes.

### 3.10. `notifications` (thông báo cần người dùng tương tác)
| Cột | Kiểu | Ghi chú |
|-----|------|--------|
| user_id | FK users, index | người nhận (với `CONFIRM`: các MAINTAINER của project; với `INPUT`: reporter + MAINTAINER) — một dòng/người nhận |
| project_id / workflow_id / ticket_id | FK | để hiển thị đường dẫn `Project / Workflow / #BUG-104` |
| type | String(10) | `CONFIRM` (chờ xác nhận trước khi @leader commit/push) \| `INPUT` (agent hỏi thêm thông tin) |
| title | String(200) | VD “Xác nhận bản sửa lỗi để @leader commit & push”, “@ba cần bạn trả lời để lập kịch bản” |
| body | String(500) | mô tả ngắn |
| gate_key | String(100) | `(ticket_id, node_id, interrupt_seq)` — **unique** để idempotent khi node chạy lại sau resume |
| is_read | Boolean | mặc định false; mở ticket từ thông báo → true |
| resolved_at | DateTime nullable | null = **Cần xử lý**; có giá trị = **Đã xử lý** (vẫn lưu làm lịch sử) |
| outcome | String(20) nullable | `APPROVED` \| `REJECTED` \| `ANSWERED` \| `CANCELLED` \| `FAILED` |
Index (user_id, resolved_at, created_at desc).

Vòng đời: engine tạo khi phát `gate_waiting` (Phase 3 §6.2–6.3) → resolve khi `reply`/`confirm`/`cancel`/ticket `FAILED`. **Không** có thông báo cho sự kiện chỉ mang tính thông tin (agent xong việc, ticket completed…).

### 3.11. `user_preferences`
`user_id`, `key` String(60), `value` JSON; PK (user_id, key). Khoá đang dùng: `default_mention_agent_id` (agent mặc định của nút @ trong composer — áp dụng cho mọi ticket), `sidebar.open.<project_id>` (tuỳ chọn, thay cho localStorage nếu muốn đồng bộ thiết bị).

## 4. Models catalog (`config/models_catalog.yaml`)
```yaml
claude-code:
  - { id: "sonnet", label: "Claude Sonnet (mặc định, coding)" }
  - { id: "opus",   label: "Claude Opus (suy luận sâu)" }
  - { id: "haiku",  label: "Claude Haiku (nhanh, nhẹ)" }
codex:
  - { id: "default", label: "Codex mặc định" }   # điền tên model thực tế sau spike Phase 0
```
- `GET /api/agents/models-catalog` trả file này, **merge** thêm danh sách model adapter báo về (nếu spike xác nhận `session/new` trả `models`) — cache 10 phút.
- Cho phép người dùng nhập model tự do (combobox) nếu không có trong danh sách.

## 5. Schema đồ thị workflow (`schemas/workflow.py`) — dùng chung với Phase 3 & 5
```jsonc
{
  "nodes": [
    {"id": "start",   "type": "start",      "position": {"x":0,"y":0}, "data": {}},
    {"id": "n_ba",    "type": "agent",      "position": {...}, "data": {"agent_id": "uuid", "instructions": "(tùy chọn, ghép thêm vào prompt)", "routing": "ba"}},
    {"id": "g_clar",  "type": "human_input","data": {"label": "BA hỏi lại người dùng"}},
    {"id": "n_dev",   "type": "agent",      "data": {"agent_id": "uuid", "routing": "none"}},
    {"id": "n_test",  "type": "agent",      "data": {"agent_id": "uuid", "routing": "tester"}},
    {"id": "g_conf",  "type": "human_confirm","data": {"message": "Bạn xác nhận lỗi đã được sửa xong?"}},
    {"id": "n_lead",  "type": "git_release","data": {"agent_id": "uuid (leader)", "push": true}},
    {"id": "end",     "type": "end",        "data": {}}
  ],
  "edges": [
    {"id":"e1","source":"start","target":"n_ba"},
    {"id":"e2","source":"n_ba","sourceHandle":"need_info","target":"g_clar"},
    {"id":"e3","source":"g_clar","target":"n_ba"},
    {"id":"e4","source":"n_ba","sourceHandle":"ready","target":"n_dev"},
    {"id":"e5","source":"n_dev","target":"n_test"},
    {"id":"e6","source":"n_test","sourceHandle":"fail","target":"n_dev"},
    {"id":"e7","source":"n_test","sourceHandle":"pass","target":"g_conf"},
    {"id":"e8","source":"g_conf","sourceHandle":"approved","target":"n_lead"},
    {"id":"e9","source":"g_conf","sourceHandle":"rejected","target":"n_dev"},
    {"id":"e10","source":"n_lead","target":"end"}
  ]
}
```
**Node types & output handles**

| type | Ý nghĩa | sourceHandle hợp lệ |
|------|---------|---------------------|
| `start` | Nhận ticket | (mặc định) |
| `agent` + `routing: none` | Agent chạy 1 lượt rồi đi tiếp | (mặc định) |
| `agent` + `routing: ba` | Agent có thể hỏi lại user | `need_info`, `ready` |
| `agent` + `routing: tester` (hoặc `review`) | Agent phán quyết đạt/không | `pass`, `fail` |
| `condition` | Rẽ nhánh theo biểu thức state (VD `state.test_passed == true`) | `true`, `false` |
| `human_input` | Dừng chờ user trả lời tự do | (mặc định) |
| `human_confirm` | Dừng chờ user duyệt | `approved`, `rejected` |
| `git_release` | Leader review + backend commit/push | `success`, `failed` (tùy chọn) |
| `end` | Kết thúc | — |

**Luật validate** (`services/workflow_validator.py`, chạy khi lưu, trả list lỗi tiếng Việt):
1. Đúng 1 `start`, ≥ 1 `end`; mọi node reachable từ `start`; mọi node có đường tới `end`.
2. Node có nhiều handle bắt buộc phải nối đủ các handle (VD tester phải có cả `pass` và `fail`).
3. `agent_id` phải thuộc *effective agents* của project và `is_active`.
4. `git_release` chỉ chấp nhận agent có `permission_profile.can_git_release = true`, và **mọi đường từ start tới `git_release` phải đi qua ít nhất một `human_confirm` (nhánh `approved`)**.
5. Chu trình (vòng lặp) cho phép, nhưng mỗi vòng phải chứa ít nhất 1 agent node (tránh loop rỗng).
6. Agent `runtime = openai-api` **không** được đặt ở node `git_release` và không được là agent duy nhất ở node cần sửa file/chạy test (node có `routing: tester` yêu cầu agent có `allow_terminal`); lỗi tiếng Việt: “@x dùng OpenAI Custom chỉ trả lời văn bản, không thể sửa file / chạy test / phát hành Git”.

## 6. REST API
Prefix `/api`, JSON, lỗi theo dạng `{"detail": "...", "code": "..."}`. Tất cả (trừ login) yêu cầu `Authorization: Bearer <jwt>`.

### 6.1. Auth & Users
| Method | Path | Mô tả |
|--------|------|------|
| POST | `/auth/login` | `{email, password}` → `{access_token, user}` |
| GET | `/auth/me` | |
| GET/POST | `/users` | ADMIN tạo user |
| PATCH | `/users/{id}` | |
Lần chạy đầu: nếu chưa có user → tạo OWNER từ biến môi trường `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`.

### 6.2. Agents
| Method | Path | Mô tả |
|--------|------|------|
| GET | `/agents?active=true` | list |
| POST | `/agents` | tạo custom agent (validate handle, runtime, profile; `is_builtin=false`). Với `runtime="openai-api"`: bắt buộc `base_url`, `model` (nhập tự do), `api_key`; **permission profile phải là `read_only` hoặc `custom` không ghi/chạy lệnh** (`allow_write=false`, `allow_terminal=false`, `can_git_release=false`) → vi phạm 422. Response chỉ có `has_key` + `api_key_last4`, không có key |
| GET | `/agents/{id}` | |
| PATCH | `/agents/{id}` | **handle không bao giờ đổi được**; built-in: cho sửa prompt/model/runtime/description/logo, không đổi role_key. Nếu body làm thay đổi ≥ 1 trường cấu hình → `config_version += 1`, gọi `ACPProcessPool.restart_agent(id)` (Phase 1 §3.6) và trả `{agent, restart: true}`; body không đổi gì → `{agent, restart: false}` (không restart). Sau khi restart xong phát WS `agent_restarted` |
| POST | `/agents/{id}/restart` | khởi động lại thủ công (cùng cơ chế) |
| GET | `/agents/{id}/usage` | `{running_tickets: [{id, code, title, status}], teams: [...], workflows: [...]}` — UI dùng để cảnh báo trước khi lưu (“N ticket đang dùng @x”) |
| DELETE | `/agents/{id}` | 409 nếu `is_builtin`, đang được dùng trong graph của workflow chưa archived, là thành viên duy nhất của một AI Team, hoặc ticket đang chạy → gợi ý deactivate |
| POST | `/agents/{id}/duplicate` | nhân bản agent (đổi handle) |
| POST | `/agents/test-connection-draft` | kiểm tra form chưa lưu cho `openai-api`: `{base_url, api_key, model, extra_headers?}` → gọi `GET {base_url}/models` (fallback: completion 1 token) → `{ok, status, latency_ms, models?: [..], error?}`; dùng để điền gợi ý model. Rate-limit 10/phút/user; không lưu key |
| POST | `/agents/{id}/test-connection` | spawn ACP (Phase 1) trong thư mục tạm, `initialize` + `session/new`, đóng → `{ok, runtime_version, latency_ms, error?}` — timeout 30s |
| GET | `/agents/models-catalog` | mục 4 |
| POST | `/assets/logo` | multipart ảnh png/jpg/webp ≤ 300KB (sanitize/resize 256px) → `{logo_url}`; dùng cho agent và team |
| GET | `/agents/permission-presets` | các preset: `read_only`, `developer`, `tester`, `leader`, `custom` |

### 6.3. AI Teams
`GET/POST /teams` (POST body bắt buộc `agent_ids` có ≥ 1 phần tử; có `icon`/`logo_url`), `GET/PATCH/DELETE /teams/{id}` (sửa team **không** khởi động lại agent nào), `PUT /teams/{id}/agents` body `{agent_ids: [...]}` (thay thế toàn bộ, giữ thứ tự; rỗng → 422 “AI Team phải có ít nhất 1 agent”).

### 6.4. Projects & Members
| Method | Path | Mô tả |
|--------|------|------|
| GET/POST | `/projects` | POST `{name, workspace_path, default_branch, description?}` → validate workspace (mục 7) → **tạo project trống**, set `last_activity_at=now`. GET hỗ trợ `?sort=recent&limit=5` (sidebar) và `?limit=` + tổng số (modal “Xem tất cả”) |
| GET/PATCH/DELETE | `/projects/{id}` | |
| POST | `/projects/validate-workspace` | `{path}` → `{exists, is_git_repo, current_branch, remotes, dirty_files_count, within_allowed_roots}` |
| GET | `/projects/{id}/members` | trả 3 nhóm users/agents/teams kèm thông tin hiển thị |
| POST | `/projects/{id}/members` | `{member_type, member_id, project_role?}` |
| DELETE | `/projects/{id}/members/{member_type}/{member_id}` | |
| GET | `/projects/{id}/effective-agents` | agent lẻ ∪ agent từ team |
| POST | `/projects/{id}/seed-default` | thêm AI Team mặc định vào project + tạo workflow **Fix Bug** (prefix `BUG`) từ template và xuất bản luôn |
| GET | `/projects/recent?limit=5&pin=<current_project_id>` | 5 project gần nhất theo `last_activity_at`; nếu `pin` không nằm trong top 5 thì thay phần tử thứ 5 bằng project đó |
| GET | `/projects/{id}/tree` | dữ liệu cho sidebar: `{project, workflows: [{id, name, prefix, status, tickets: [{id, code, channel_slug, title, status, updated_at}] (≤ 15 mới nhất)}]}` |

### 6.5. Workflows (bước 2 trong thứ tự tạo)
| Method | Path | Mô tả |
|--------|------|------|
| GET | `/projects/{id}/workflows?include_archived=false` | danh sách workflow của project + số ticket theo trạng thái |
| POST | `/projects/{id}/workflows` | `{name, ticket_prefix, description?, template?: "blank" \| "bugfix_default" \| "bugfix_with_security_review"}` → `DRAFT` (template thì graph điền sẵn) |
| GET | `/workflows/{wid}` | gồm graph nháp, `published_version`, `is_valid` |
| PATCH | `/workflows/{wid}` | sửa name/prefix/description/icon/position (prefix chỉ sửa được khi chưa có ticket) |
| PUT | `/workflows/{wid}/graph` | lưu graph nháp → `current_version+1`, validate, trả `{current_version, is_valid, errors}` |
| POST | `/workflows/{wid}/validate` | validate không lưu |
| POST | `/workflows/{wid}/publish` | 400 nếu invalid; tạo `workflow_versions`, set `PUBLISHED` |
| POST | `/workflows/{wid}/duplicate` | nhân bản thành workflow DRAFT mới (đổi name/prefix) |
| POST | `/workflows/{wid}/archive` / `/unarchive` | xem quy tắc 3.6 |
| DELETE | `/workflows/{wid}` | chỉ khi chưa có ticket |
| GET | `/workflows/{wid}/versions` | lịch sử version đã xuất bản |
| GET | `/workflows/{wid}/versions/{v}` | graph của một version (cửa sổ chat dùng để vẽ tiến độ đúng version của ticket) |
| GET | `/workflow-templates` | list template |

### 6.6. Tickets (bước 3 — luôn tạo bên trong một workflow)
| Method | Path | Mô tả |
|--------|------|------|
| GET | `/workflows/{wid}/tickets?status=&q=` | ticket của một workflow |
| GET | `/projects/{id}/tickets?workflow_id=&status=&q=` | toàn project (khối “Ticket gần đây”, lọc) |
| POST | `/workflows/{wid}/tickets` | `{title, description, auto_start: true}` → 400 nếu workflow chưa `PUBLISHED` hoặc `ARCHIVED`; tạo ticket `OPEN` với `workflow_version = published_version`; nếu `auto_start` (mặc định) thì gọi `TicketRunner.start` (Phase 3) ngay. Trả `{ticket, chat_url: "/projects/{pid}/workflows/{wid}/tickets/{tid}"}` để frontend mở cửa sổ chat |
| GET | `/tickets/{tid}` | |
| PATCH | `/tickets/{tid}` | sửa title/description khi `OPEN` |
| GET | `/tickets/{tid}/messages?after_seq=&limit=200` | lịch sử chat |
| POST | `/tickets/{tid}/attachments` | multipart 1 file → `{id, filename, mime, size, url, thumbnail_url}`; vi phạm giới hạn → 413/422 |
| GET | `/attachments/{id}` | tải/hiển thị file (kiểm tra quyền theo ticket) |
| GET | `/tickets/{tid}/logs?agent=&after_seq=&limit=` | **log agent** của ticket: các event `tool_call`, `tool_call_update`, `permission`, `thought_chunk`, `plan`, `error` + dòng hệ thống đã chuẩn hoá `{seq, run_id, agent, kind, text, at}` — nguồn cho `AgentLogDialog`; phần log gắn từng lượt chat lấy từ chính event stream theo `run_id` |

### 6.7. Notifications (thay cho “Hộp thư”)
| Method | Path | Mô tả |
|--------|------|------|
| GET | `/notifications?status=open\|resolved&limit=&cursor=` | danh sách của user hiện tại, mới nhất trước; mỗi item có `type, title, body, project, workflow, ticket{id,code,title}, is_read, created_at, resolved_at, outcome` |
| GET | `/notifications/unread-count` | `{open: n}` — số **chưa xử lý** (badge sidebar) |
| POST | `/notifications/{id}/read` | đánh dấu đã đọc (khi click mở ticket) |
| POST | `/notifications/read-all` | nút “Đánh dấu đã đọc” |
Không có API client tự resolve: backend resolve khi nhận `reply`/`confirm`/`cancel`. Realtime: `WS /ws/users/me` phát `notification_created`, `notification_resolved`.

### 6.8. Preferences
`GET /me/preferences`, `PUT /me/preferences` `{key, value}` — dùng cho `default_mention_agent_id`.

## 7. Workspace validator
- Path tuyệt đối, tồn tại, là thư mục, nằm trong `ALLOWED_WORKSPACE_ROOTS`.
- `git rev-parse --is-inside-work-tree`, `git branch --show-current`, `git remote -v`, `git status --porcelain` (đếm file dirty). Chạy bằng subprocess với timeout 10s.
- Cảnh báo (không chặn) nếu repo đang dirty — UI hiển thị.

## 8. Seed (`services/seed.py`, chạy idempotent ở startup)
4 agent built-in (runtime/model mặc định có thể sửa sau):

| handle | display_name | role_key | runtime | icon/color | preset quyền |
|-------|--------------|----------|---------|------------|--------------|
| `@ba` | Business Analyst | BA | claude-code | 🐝 / sky | read_only |
| `@developer` | Frontend Developer | DEVELOPER | claude-code | 🛠️ / amber | developer |
| `@tester` | QA Tester | TESTER | codex | 🧪 / emerald | tester |
| `@leader` | Tech Lead (Git Release) | LEADER | claude-code | 🚀 / purple | leader (`can_git_release=true`) |

System prompt mặc định (lưu ở `app/engine/prompts.py` → `DEFAULT_SYSTEM_PROMPTS`, nội dung lấy từ PDF, rút gọn):
- **@ba**: “Bạn là Business Analyst của dự án. Tiếp nhận phản ánh lỗi; đọc mã nguồn (chỉ đọc) để hiểu ngữ cảnh; viết kịch bản tái tạo lỗi (STR) gồm điều kiện tiên quyết, các bước, kết quả thực tế, kết quả mong muốn, file/màn hình liên quan. Nếu thiếu thông tin thì hỏi lại người dùng tối đa 3 câu rõ ràng. Không sửa file, không chạy git.”
- **@developer**: “Bạn là Developer. Nhận STR từ @ba (hoặc phản hồi lỗi từ @tester/người dùng); tìm nguyên nhân gốc, sửa code trực tiếp trong workspace; chạy build/lint/test liên quan. TUYỆT ĐỐI KHÔNG chạy git commit, git push, git merge, git reset. Cuối lượt tóm tắt nguyên nhân, cách sửa, danh sách file đã sửa.”
- **@tester**: “Bạn là QA. Đối chiếu thay đổi (git diff) với STR; chạy test liên quan; không sửa mã nguồn ứng dụng, không chạy git commit/push. Kết luận ĐẠT hoặc CHƯA ĐẠT kèm lý do cụ thể.”
- **@leader**: “Bạn là Tech Lead. Chỉ hoạt động sau khi người dùng xác nhận. Review git diff: phát hiện file rác, file nhạy cảm (.env, log), code vi phạm chuẩn. Đề xuất danh sách file cần commit và commit message theo Conventional Commits. Không tự chạy git add/commit/push — hệ thống sẽ thực thi.”

AI Team mặc định: **Core Bugfix Squad** = 4 agent trên. Template workflow `bugfix_default` = graph ở mục 5. Seed **không** tạo project/workflow nào — project và workflow do người dùng tạo theo đúng thứ tự (hoặc qua `seed-default` của từng project).

## 9. Test
- `tests/api/test_agents.py`: tạo `@security_checker` (codex, profile read_only) OK; handle sai format → 422; trùng → 409; xóa built-in → 409.
- `test_projects.py`: workspace ngoài allowed roots → 400; member TEAM → effective-agents gồm agent của team; xóa team member → agent biến mất khỏi effective.
- `test_teams.py`: tạo team không có agent → 422; gỡ agent cuối cùng → 422; xóa agent là thành viên duy nhất của team → 409.
- `test_workflows.py`: một project tạo được 2 workflow (prefix khác nhau), prefix trùng → 409; template mặc định valid; thiếu nhánh `fail` → invalid; `git_release` không có `human_confirm` phía trước → invalid; `current_version` tăng khi lưu; publish invalid → 400; archive workflow cuối cùng có ticket → 409.
- `test_tickets.py`: tạo ticket trong workflow `DRAFT` → 400; ticket lưu đúng `workflow_version`; xuất bản lại workflow không đổi version của ticket cũ; mã `#BUG-1`, `#FEAT-2` dùng chung bộ đếm project; channel_slug từ “Đơ nút Xuất Excel báo cáo” (prefix BUG) → `bug-do-nut-xuat-excel-bao-cao` (cắt ≤ 40).
- `test_tree.py`: `/projects/{id}/tree` trả đúng cây workflow → ticket.
- `test_seed.py`: chạy seed 2 lần không nhân đôi dữ liệu.
- `test_agents_api_runtime.py`: tạo agent `openai-api` đầy đủ → 201, response không chứa key, DB lưu `api_key_enc` ≠ plaintext; thiếu base_url/api_key/model → 422; preset `developer`/`tester` hoặc `can_git_release=true` → 422; `base_url` nội bộ/metadata → 422; PATCH không gửi `api_key` → giữ key cũ, gửi key mới → đổi + restart; đổi runtime từ `claude-code` sang `openai-api` → profile bị buộc về read-only; `test-connection-draft` với fake server trả danh sách model; log/audit không chứa key.
- `test_agents_edit.py`: PATCH đổi model → `restart=true`, `config_version` +1, pool gọi `restart_agent`; PATCH body giống cũ → `restart=false`; đổi handle → 422; chỉ đổi thành viên team → không restart; logo upload > 300KB → 413.
- `test_projects_recent.py`: tạo project → xuất hiện đầu `/projects/recent`; mở/GET project không đổi thứ tự; tạo ticket ở project cũ → project đó lên đầu; `pin` ngoài top 5 thay phần tử thứ 5; `POST /projects` không cần team/workflow.
- `test_notifications.py`: ticket vào `WAITING_USER_CONFIRM` → tạo đúng 1 thông báo/người nhận (chạy lại node không nhân đôi nhờ `gate_key`); `confirm` → `resolved_at`, `outcome=APPROVED`, vẫn hiện ở `status=resolved`; `unread-count` giảm; huỷ ticket → `CANCELLED`.
- `test_attachments.py`: 6 file/tin nhắn → lỗi; file 11MB → lỗi; ảnh có thumbnail; file chưa gắn tin nhắn quá 24h bị dọn.

## 10. Definition of Done

Bằng chứng, cấu hình và điểm tích hợp Phase 3: [PHASE_2_IMPLEMENTATION_NOTES.md](PHASE_2_IMPLEMENTATION_NOTES.md).

- [x] `alembic upgrade head` tạo đủ bảng trên SQLite và PostgreSQL.
- [x] Khởi động server → có 4 agent built-in + team mặc định.
- [x] `POST /api/projects` với `D:\VETC\FE\HNBG_DEV` → validate đúng branch hiện tại.
- [x] `POST /api/projects/{id}/seed-default` → project có workflow *Fix Bug* `PUBLISHED`, `is_valid=true`.
- [x] Tạo project trống (không team/workflow) thành công; `/projects/recent` ổn định theo `last_activity_at`.
- [x] Sửa agent → restart đúng; thông báo tạo/resolve đúng theo gate; đính kèm có giới hạn.
- [x] Đi đúng thứ tự project → workflow → ticket qua API; mọi đường tắt sai thứ tự (ticket không có workflow, workflow chưa xuất bản) đều bị chặn.
- [x] OpenAPI (`/docs`) đầy đủ để frontend Phase 4 sinh type từ OpenAPI (`openapi-typescript`); việc sinh type/giao diện thực hiện ở Phase 4.
