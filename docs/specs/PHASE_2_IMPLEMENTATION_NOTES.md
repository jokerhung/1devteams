# Phase 2 — Database & REST API

## Đã triển khai

- SQLAlchemy 2 async, UUID, JSON dùng chung SQLite/PostgreSQL; Alembic revision `0001` tạo
  14 bảng nghiệp vụ và đầy đủ index/FK/unique constraints. `team_agents` và `user_preferences`
  dùng khóa chính ghép như đặc tả.
- Startup chạy migration, seed idempotent 4 built-in agents và Core Bugfix Squad; không tự tạo project.
- JWT có hạn dùng, bcrypt, bootstrap OWNER, quyền OWNER/ADMIN và quyền theo project.
  Owner project có quyền MAINTAINER ngầm định; project mới không tạo dòng member nào.
  MEMBER có thể tạo project; VIEWER chỉ đọc; REPORTER có thể tạo/sửa ticket OPEN;
  MAINTAINER quản lý project/workflow/member. Quản lý agent/team/user yêu cầu ADMIN/OWNER.
- CRUD agents/teams/projects/members; agent API text-only; API key và toàn bộ extra headers mã hóa
  Fernet, không xuất credential ra response hoặc lỗi validation. Handle bất biến, built-in role bất biến.
- PATCH cấu hình agent có thay đổi tăng version và gọi pool restart; request không đổi không restart.
  Xóa agent cũng đóng session còn lưu. Sửa thành viên team không restart agent.
- Models catalog YAML + kết quả handshake được ghi nhận khi test connection, cache 10 phút.
  Model tự do được chấp nhận. Test connection bị giới hạn 10 lần/phút/user, timeout 30 giây;
  probe HTTP dùng URL policy và IP pinning từ Phase 1.
- Workflow templates, graph validation, publish snapshot bất biến, duplicate/archive/version history.
  Kiểm tra mọi đường tới git_release đều qua cạnh approved của human_confirm; kiểm tra từng chu trình
  không có agent. Template security review cần bổ sung agent có role_key SECURITY vào project.
- Ticket giữ snapshot version, bộ đếm project atomic, slug tiếng Việt ≤40 ký tự, recent/tree,
  lịch sử message theo seq và log theo run/agent. Các mutation workflow dùng khóa project để serialize
  điều kiện archive và version; tạo ticket kiểm tra lại snapshot cùng effective agents hiện tại.
- Notification service tạo gate idempotent theo `(user_id, gate_key)`, resolve và EventBus theo user;
  inbox/cursor/read/count. OWNER project nhận gate cùng MAINTAINER; INPUT thêm reporter.
- `WS /ws/users/me`: nhận notification events và agent restart events; xác thực và lọc quyền project.
- Preferences; upload logo sanitize/resize 256px; upload attachment, kiểm tra magic bytes/script/size/count,
  thumbnail, tải file theo quyền ticket, helper gắn tệp vào message, dọn tệp chờ quá 24h lúc startup
  và mỗi giờ. File đính kèm tải dạng attachment, kèm nosniff/CSP sandbox.
- OpenAPI có request/response schemas và lỗi `{detail, code}`; không trả raw input trong validation errors.
  `/api/health` giữ công khai để launcher và màn hình health Phase 0 tiếp tục hoạt động.

## Cấu hình lần đầu

Tại `backend/.env`:

```dotenv
JWT_SECRET=<chuỗi ngẫu nhiên riêng>
APP_SECRET_KEY=<khóa Fernet tạo một lần>
BOOTSTRAP_ADMIN_EMAIL=owner@example.com
BOOTSTRAP_ADMIN_PASSWORD=<mật khẩu ít nhất 8 ký tự, tối đa 72 byte UTF-8>
DATABASE_URL=sqlite+aiosqlite:///./aiteams.db
ALLOWED_WORKSPACE_ROOTS=D:\VETC
ATTACH_MAX_FILES=5
ATTACH_MAX_MB=10
ATTACH_ALLOW_SCRIPTS=false
```

Tạo khóa Fernet bằng lệnh sau; đặt kết quả vào `.env`, giữ khóa ổn định khi restart và backup cùng database:

```powershell
cd backend
uv sync --frozen --python 3.12
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
uv run alembic upgrade head
```

Chỉ tạo OWNER từ bootstrap nếu database chưa có user. Không có tài khoản/mật khẩu mặc định được hard-code.
Thiếu APP_SECRET_KEY vẫn dùng native-agent configuration được, nhưng lưu/giải mã credential API sẽ trả 503.
Thiếu bootstrap trên DB trống thì chưa đăng nhập được; đặt email/password rồi khởi động lại.
`DATABASE_URL` tương đối SQLite được neo vào `backend/`, tránh tạo nhầm DB theo thư mục gọi script.
PostgreSQL dùng `postgresql+asyncpg://user:password@host/database` (database phải tồn tại).
Blob được lưu mặc định tại `backend/data/`; backup thư mục này cùng database.

Từ root repo chạy `./scripts/dev.ps1`, truy cập Swagger `http://localhost:8060/docs`.
Đăng nhập `POST /api/auth/login`, dùng `access_token` tại nút Authorize của Swagger.
Luồng API: tạo project → thêm team/agent → tạo/lưu graph workflow → publish → tạo ticket.
`POST /api/projects/{id}/seed-default` thực hiện thêm default team và tạo/publish Fix Bug.

## Ranh giới Phase 3

Phase 2 cung cấp dữ liệu và API quản trị, không thực thi workflow. Ticket mới giữ OPEN;
`auto_start=true` trả `auto_start_pending=true` nếu chưa có `app.state.ticket_runner`.
Khi Phase 3 gắn runner, endpoint sẽ gọi `await runner.start(ticket.id)` sau commit.

`notification_service.create_gate/resolve_gate`, `ticket_service.add_message` và
`assets.attach_to_message` là các điểm tích hợp cho runner/reply/confirm/cancel.
Không có HTTP endpoint cho client tự resolve notification. Kiểm thử gọi các service này trực tiếp
để xác minh dữ liệu và event; tương tác chạy workflow/reply/confirm/cancel thuộc Phase 3.

Native runtime policy gate của Phase 1 vẫn còn hiệu lực. Endpoint test connection chỉ handshake
trong thư mục tạm, không gửi prompt; thành công không chứng minh tool sandbox hoặc inference.
Model catalog chỉ chứa cấu hình và thông tin adapter đã quan sát, không cam kết provider còn cấp model đó.

Browser WebSocket gửi frame đầu `{"token":"<access_token>"}` trong 5 giây, rồi chờ
`{"event_type":"connected"}`. Native client có thể dùng header Authorization. Không đặt JWT vào query URL.

## Kiểm chứng (2026-10-23)

- Windows Python 3.12 + SQLite: **125 passed, 1 skipped, 3 deselected**. Test symlink
  bị bỏ qua vì host không có quyền tạo symlink; 3 bài inference thật của Phase 1 là opt-in.
- PostgreSQL 16: **38 passed**; toàn bộ API integration suite chạy trên database riêng cho từng test,
  kiểm tra migration/schema/downgrade và bộ đếm đồng thời.
- Linux Python 3.12 + SQLite: **126 passed, 3 deselected** trong Docker, source mount read-only.
- Ruff lint/format và mypy: pass trên cả Windows và Linux.
- Workspace thật `D:\VETC\FE\HNBG_DEV`: API nhận đúng branch `master`, remote `origin`,
  nhận repo dirty (23 file), tạo project 201 và seed workflow PUBLISHED 200 trong database kiểm chứng tạm.
  Không ghi vào workspace này.
- Workflow CI đã bổ sung PostgreSQL service job bên cạnh matrix SQLite Windows/Linux;
  chưa thực thi job GitHub từ thay đổi chưa commit này.

Chạy kiểm tra:

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest

# Dùng PostgreSQL test database riêng. Tài khoản này cần quyền CREATE DATABASE.
$env:AITEAMS_TEST_POSTGRES_URL='postgresql+asyncpg://user:password@localhost/test_admin_db'
uv run pytest tests/api
Remove-Item Env:AITEAMS_TEST_POSTGRES_URL
```

Test PostgreSQL tạo/xóa database có tên `aiteams_test_<uuid>`; không dùng DB ứng dụng làm test data.
Các bài real_acp/real_api của Phase 1 vẫn opt-in và bị loại khỏi suite offline.
