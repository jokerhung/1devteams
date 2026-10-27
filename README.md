# aiTeams

Phase 1 ACP/API bridge: [implementation, usage and verification status](docs/specs/PHASE_1_IMPLEMENTATION_NOTES.md).
Phase 2 Database & REST API: [cấu hình đăng nhập, migration và API](docs/specs/PHASE_2_IMPLEMENTATION_NOTES.md).
Phase 3 Workflow Engine: [runner, checkpoint, gates, Git release và realtime](docs/specs/PHASE_3_IMPLEMENTATION_NOTES.md).
Phase 4 Frontend Shell & Management: [giao diện, đăng nhập, quản lý và kiểm thử](docs/specs/PHASE_4_IMPLEMENTATION_NOTES.md).
Phase 5 Workflow Builder: [wizard, canvas, pipeline và kiểm thử](docs/specs/PHASE_5_IMPLEMENTATION_NOTES.md).
Phase 6 Ticket Chat Runtime: [chat, log, attachments, gates và kiểm thử](docs/specs/PHASE_6_IMPLEMENTATION_NOTES.md).
Phase 7 Terminal & Hardening: [PTY, fallback, audit, backup, cài đặt và kiểm thử](docs/specs/PHASE_7_IMPLEMENTATION_NOTES.md).

Monorepo FastAPI + Next.js 15, ACP/API bridge, database/REST API, workflow engine
và giao diện quản lý, Workflow Builder, Ticket Chat Runtime. Native ACP còn bị khóa bởi policy gate
cho đến khi công cụ của adapter được cách ly và kiểm chứng; xem ghi chú Phase 3.

## Cài đặt (PowerShell)

Yêu cầu Python 3.11+ (đã kiểm tra với 3.12), uv, Node.js 22+ và npm.

```powershell
npm ci
uv sync --project backend --python 3.12
npm --prefix frontend ci
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env
```

Đặt `JWT_SECRET` riêng trong `backend/.env` (bắt buộc; không commit). Các cấu hình còn lại
có mặc định trong file mẫu. `ALLOWED_WORKSPACE_ROOTS` phân cách bằng `;`,
`CORS_ORIGINS` phân cách bằng `,`. Next proxy gọi backend qua `BACKEND_URL`
(fallback `NEXT_PUBLIC_API_URL`); browser dùng `/api/backend` cùng origin.

```powershell
.\scripts\dev.ps1
# Install/sync backend virtual environment and frontend dependencies, then start:
.\scripts\dev.ps1 -Setup
# Hoặc: npm run dev
# Kiểm tra startup rồi tự dừng cả hai dịch vụ:
.\scripts\dev.ps1 -SmokeTest
```

`scripts/dev.ps1` runs the backend with `backend/.venv/Scripts/python.exe` directly;
manual virtual environment activation is not required. Logs are written to `.dev-logs/`.
Press Ctrl+C to stop both services. `-SmokeTest` checks both URLs and then stops them.

Đổi cổng trong `.env` tại thư mục gốc repo rồi chạy lại script:

```dotenv
FRONTEND_PORT=3060
BACKEND_PORT=8060
```

Script tự đặt `NEXT_PUBLIC_API_URL` theo cổng backend và thêm địa chỉ frontend vào CORS.
Biến môi trường của tiến trình được ưu tiên hơn `.env`. Backend vẫn dùng virtual environment.

- Frontend: http://localhost:3060 — đăng nhập bằng tài khoản owner trong `backend/.env`, quản lý Agents & Teams, Projects và Thông báo.
- Backend: http://localhost:8060/api/health — `{"status":"ok","acp":{"claude":true,"codex":true}}`.
- Swagger: http://localhost:8060/docs.

Script dừng cả process tree khi Ctrl+C hoặc khi một dịch vụ thoát. Không dùng Uvicorn
`--reload` trên Windows để giữ ProactorEventLoop cho subprocess ACP.
Adapter được cài **trong repo** ở `node_modules/.bin`; resolver ưu tiên bản được pin này,
sau đó tìm trên PATH. Có thể override `CLAUDE_ACP_BIN` / `CODEX_ACP_BIN` bằng đường dẫn tuyệt đối.
Health chỉ xác nhận binary tồn tại, không xác nhận login hoặc inference hoạt động.

## Remote terminal

Terminal dùng WebSocket hai chiều tại `/ws/terminal/{project_id}` qua rewrite của Next.js
tới `BACKEND_URL` (hoặc `NEXT_PUBLIC_API_URL`). Reverse proxy phía trước web cần cho phép
WebSocket Upgrade. Trình duyệt dùng cookie HttpOnly; Origin phải nằm trong `CORS_ORIGINS`
và người dùng cần quyền ghi project. Quyền được kiểm tra lại tối đa mỗi 15 giây.

Output lớn được gom theo frame, phản hồi nhỏ được ghi ngay khi hàng đợi rảnh. WebGL tự
chuyển về renderer mặc định nếu không khả dụng hoặc mất context. Khi tự kết nối lại,
client gửi `session_id` và `after_seq` để lấy bù output. Backend giữ tối đa 262144 ký tự
và 4096 chunk; nếu phần còn thiếu đã bị loại khỏi bộ đệm, terminal được reset và phát
lại phần lịch sử còn giữ. Phản hồi giao thức sinh từ lịch sử không gửi ngược vào shell.

PTY hiện vẫn thuộc tiến trình backend: mất kết nối web giữ shell đến thời hạn idle,
nhưng restart backend sẽ kết thúc shell. Chỉ cần tách PTY daemon khi có yêu cầu giữ
shell qua restart; daemon chưa thuộc thay đổi này.

## Kiểm tra

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
cd ../frontend
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npm run test:e2e
```

## Spike ACP thật

Chạy `claude auth status` và `codex login status` để tự kiểm tra đăng nhập.
Không đưa API key hay output chứa credential vào issue/log công khai.

```powershell
cd backend
uv run python scripts/acp_spike.py --runtime claude
uv run python scripts/acp_spike.py --runtime codex --mode read-only
```

Harness tạo workspace nhỏ trong thư mục Temp của Windows, độc lập với repo; giữ lại để
kiểm tra kết quả. Permission `allow_once` chỉ dùng cho spike trong workspace dùng một lần.
Harness không phải sandbox bảo mật cho agent hoặc lệnh terminal tùy ý.

Mỗi lượt lưu stdout nguyên dòng (`.ndjson`), các message client gửi (`.client.ndjson`),
stderr (`.stderr.log`) và kết quả từng bước (`.summary.json`) ở `backend/spike_logs/`
(gitignored). `--timeout`, `--cancel-after`, `--mode`, `--model`, `--binary` cho phép tái lập kiểm tra.
Summary có `checks` và `passed`; full spike chỉ trả exit code 0 khi chọn model, kết thúc prompt,
nội dung hello.txt, marker vai trò BA và hủy lượt pending đều được xác minh. Các chế độ
`--skip-cancel`/`--cancel-only` chỉ xác minh phần tương ứng, không chứng minh full spike.
Claude dùng `session/set_config_option`; Codex dùng `session/set_model` theo kết quả thật.
`--isolate-settings` chỉ loại trừ settings cá nhân trong session Claude đang thử.

```powershell
uv run python scripts/sanitize_spike.py spike_logs/<stem>.ndjson tests/fixtures/acp/claude.ndjson
```

Đọc và kiểm tra log đã khử thông tin trước khi commit. Xem kết quả, khác biệt giao thức và
các phần chưa xác minh tại [ACP_SPIKE_NOTES](docs/specs/ACP_SPIKE_NOTES.md).
