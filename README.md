# aiTeams

Phase 1 ACP/API bridge: [implementation, usage and verification status](docs/specs/PHASE_1_IMPLEMENTATION_NOTES.md).

Khung monorepo Phase 0: FastAPI + Next.js 15 và harness xác minh ACP thật trên Windows.
Chưa triển khai nghiệp vụ, database schema hoặc giao diện quản lý của các phase sau.

## Cài đặt (PowerShell)

Yêu cầu Python 3.11+ (đã kiểm tra với 3.12), uv, Node.js 22+ và npm.

```powershell
npm ci
uv sync --project backend --python 3.12
npm --prefix frontend ci
Copy-Item .env.example .env
Copy-Item backend/.env.example backend/.env
Copy-Item frontend/.env.example frontend/.env.local
```

Đặt `JWT_SECRET` riêng trong `backend/.env` (bắt buộc; không commit). Các cấu hình còn lại
có mặc định trong file mẫu. `ALLOWED_WORKSPACE_ROOTS` phân cách bằng `;`,
`CORS_ORIGINS` phân cách bằng `,`. API wrapper dùng `NEXT_PUBLIC_API_URL`.

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

- Frontend: http://localhost:3060 — trang health có nút kiểm tra lại, loading và lỗi kết nối.
- Backend: http://localhost:8060/api/health — `{"status":"ok","acp":{"claude":true,"codex":true}}`.
- Swagger: http://localhost:8060/docs.

Script dừng cả process tree khi Ctrl+C hoặc khi một dịch vụ thoát. Không dùng Uvicorn
`--reload` trên Windows để giữ ProactorEventLoop cho subprocess ACP.
Adapter được cài **trong repo** ở `node_modules/.bin`; resolver ưu tiên bản được pin này,
sau đó tìm trên PATH. Có thể override `CLAUDE_ACP_BIN` / `CODEX_ACP_BIN` bằng đường dẫn tuyệt đối.
Health chỉ xác nhận binary tồn tại, không xác nhận login hoặc inference hoạt động.

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
npm run build
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
