# Phase 7 — Terminal, fallback và vận hành

## Phạm vi đã triển khai

- PTY thật: Windows `pywinpty`, POSIX `ptyprocess`; shell không kế thừa biến môi trường
  chứa credential của backend. Một phiên/user/project, giới hạn tổng số phiên,
  giữ output gần nhất và giữ shell 10 phút sau khi ngắt kết nối.
- `WS /ws/terminal/{project_id}` kiểm tra đăng nhập, quyền MAINTAINER/owner/admin,
  workspace root, Origin khi có và kiểm tra lại quyền trong suốt phiên.
- Drawer Terminal dùng xterm, Fit/Web Links, dark theme, resize, reconnect cùng phiên,
  clear, copy và lệnh nhanh. Browser dùng SSE cùng origin + REST input; JWT vẫn ở cookie
  httpOnly và proxy server. WebSocket trực tiếp cũng hỗ trợ input/resize.
- Terminal mặc định **tắt**. Đây là shell với quyền tài khoản chạy backend, không qua
  Permission Guard của agent. Chỉ bật cho người quản trị workspace đáng tin cậy.
- Retry quá tải 30/60 giây, tối đa hai lần, tôn trọng `Retry-After`; 401/403/404 không retry.
  Sau đó chuyển model/runtime dự phòng hoặc agent API riêng cho vai trò text-only.
  Vẫn lỗi thì mở human input gate, đổi model trong Agents rồi trả lời để chạy lại node.
  Session được phân biệt bằng toàn bộ cấu hình để không dùng nhầm session fallback.
- Agent form cấu hình fallback; `usage` được giữ trong `agent_turn_end`.
  Preset seed gợi ý BA/Tester dùng model nhanh, Developer/Leader dùng model mạnh,
  không pin tên model có thể hết hỗ trợ.
- Mention ngoài gate tạo ad-hoc turn và giữ nguyên trạng thái workflow; agent bận thì
  trả 409. Prompt chứa ngữ cảnh, tin nhắn và đường dẫn attachment. Ad-hoc không gọi
  Git release. Lượt có quyền ghi giữ lock tới khi workflow tiếp tục hoặc ticket bị huỷ;
  dấu hiệu giữ workspace được lưu để khôi phục sau restart.
- Dừng agent ngay trong lượt; huỷ ticket đóng session và nhả lock. Ticket đã huỷ có thể
  cất thay đổi vào `git stash push -u`, có xác nhận UI và kiểm tra MAINTAINER/workspace rảnh.
  Không dùng reset/checkout để xoá thay đổi.
- Quota attachment/ticket, dọn pending sau 24 giờ, MIME/magic bytes và chặn executable,
  resize logo đã có từ Phase 6. Xoá ticket/project dọn file và checkpoint tương ứng.
- Giới hạn ACP/API, terminal, số ticket đồng thời, timeout mỗi lượt. Event lớn được cắt
  trước khi lưu DB; bản JSON đã scrub đầy đủ nằm trong `data/blobs/events`, tải qua API
  có kiểm tra quyền ticket. Chat hiển thị liên kết tải.
- Migration `0002_phase7`: fallback config, `audit_logs`, `terminal_audit`.
  Audit agent create/update/permission/restart (ticket bị ảnh hưởng), gates, release,
  terminal open/close và stash. `/settings/audit` dành cho admin.
- JSON log có scrub credential; không ghi query token nguyên bản.
  `/api/metrics`: ticket theo status, trung bình thời gian node, guard deny.
  `/settings/adapters`: version local/global, kiểm tra bản mới từ npm.
- Script backup SQLite/checkpoints/data và xoay Fernet key cho cả API key lẫn encrypted
  extra headers; script Windows install/start, bind loopback, backend dùng `.venv`.

## Cấu hình

Thêm vào `backend/.env` khi cần; mẫu đầy đủ nằm trong `.env.example`:

```dotenv
ENABLE_REMOTE_TERMINAL=true
TERMINAL_IDLE_SECONDS=600
TERMINAL_AUDIT_INPUT=false
MAX_TERMINAL_SESSIONS=8
MAX_CONCURRENT_TICKETS=4
MAX_EVENT_CHARS=100000
ATTACH_QUOTA_MB=200
OVERLOAD_PATTERNS=capacity,overloaded,429,529,rate limit
MODEL_RETRY_DELAYS=30,60
```

Khởi động lại backend sau khi sửa cấu hình. Ghi input terminal là tuỳ chọn; mặc định tắt.
Fallback mặc định tắt; agent API dự phòng phải hoạt động, có credential riêng và là
effective agent của project. Agent cần write/terminal/release không được fallback API.

## Cài đặt và chạy Windows

Chuẩn bị Python 3.11+, uv, Node 20+, npm, Git và các file `.env` theo README.
Đặt JWT secret, Fernet key và bootstrap owner trước khi chạy:

```powershell
.\scripts\install.ps1
.\scripts\start.ps1
# Kiểm tra readiness, proxy và tự dừng:
.\scripts\start.ps1 -SmokeTest
```

Installer cài adapter local được pin trong lockfile, đồng thời cài bản global tương ứng.
Dùng `-SkipGlobalAdapters` nếu chỉ muốn adapter local. Không tự login provider.
Port lấy từ `.env` gốc (`FRONTEND_PORT=3060`, `BACKEND_PORT=8060`), biến môi trường
được ưu tiên. Start dùng `127.0.0.1`, giữ tiến trình cha để Ctrl+C dừng cả hai dịch vụ.

Truy cập từ thiết bị khác: đặt reverse proxy có HTTPS trước frontend, bật đăng nhập,
giữ backend ở loopback và cấu hình CORS theo origin thực. Không mở trực tiếp cổng
backend/PTY ra Internet. Chạy bằng một worker vì runner, pool và workspace lock nằm
trong process. NSSM là lựa chọn triển khai bên ngoài, chưa cài service tự động.

## Backup và xoay khóa

```powershell
.\scripts\backup.ps1
# Đăng ký với Task Scheduler, chạy hằng ngày lúc 02:00 bằng tài khoản Windows hiện tại:
.\scripts\backup.ps1 -RegisterDaily
```

Mặc định lưu trong `backups/` (Git ignore). SQLite online backup bao gồm WAL và có
integrity check. Mỗi DB nhất quán riêng; dừng ứng dụng trước backup nếu cần một mốc
khôi phục đồng bộ giữa DB nghiệp vụ, checkpoint và file. Archive không chứa `.env`;
lưu khóa Fernet hiện tại riêng ở nơi bảo mật. Không tự xoá backup cũ.

Xoay khóa khi ứng dụng đã dừng và đã backup:

```powershell
cd backend
# Gán giá trị vào biến, không đưa khóa vào command-line argument hoặc log.
$env:NEW_APP_SECRET_KEY = & .\.venv\Scripts\python.exe -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
.\.venv\Scripts\python.exe scripts/rotate_key.py
# Sau thành công, thay APP_SECRET_KEY trong backend/.env bằng NEW_APP_SECRET_KEY.
# Giữ bản backup với khóa cũ; khởi động lại chỉ sau khi cấu hình khóa mới.
```

Rotation giải mã toàn bộ credential trước, cập nhật trong một transaction; lỗi giải mã
sẽ rollback. Script không in khóa và không tự sửa `.env`. Nếu chưa đổi `.env` sau khi
rotation thành công, backend sẽ không đọc được credential mới.

## Kiểm chứng

- Guard: 63 chuỗi né chặn × Developer/Tester = 126 trường hợp, gồm quote/expansion,
  wrapper, alias, inline Git config, pager, redirection và Git mutation.
- Backend: **315 pass, 1 skip, 4 deselect**; hồi quy engine/API/ACP, fallback + Retry-After, gate quá tải rồi đổi model,
  401 không retry, ad-hoc/status/stop/lock/stash, quota/event blob/scrub/delete,
  backup WAL và rotation cả key/header.
- Windows PTY thật: nhập lệnh, resize, reconnect cùng session, từ chối tab thứ hai,
  đóng process sau timeout và audit open/close.
- Frontend: 29 unit test, lint, TypeScript, production build.
- E2E: 5 bài hồi quy Phase 4–6 pass; bài terminal riêng pass trên Chromium với
  PTY Windows thật, `git status`, resize/reconnect, audit và VIEWER bị từ chối.
- PowerShell install/start/backup parse thành công. Production `start.ps1 -SmokeTest`
  pass trên cổng 3063/8063 với SQLite/checkpoint riêng, không đụng DB local đang dùng.

## Nghiệm thu cần môi trường riêng

Không đánh dấu hoàn tất nghiệm thu cài đặt trên **Windows sạch**: phiên này kiểm tra
trên máy phát triển đã có dependencies. Linux/macOS PTY chưa chạy trên máy này.
Chưa chạy provider inference bằng credential thật trong Phase 7.

Native ACP vẫn bị policy gate từ Phase 3: chưa chứng minh toàn bộ công cụ native chỉ
đi qua guard hoặc OS sandbox. Bộ lọc shell không phải sandbox; không nới gate chỉ vì
126 ca né guard pass. Checklist native happy path, clean Windows install và live
API/provider trong đặc tả vẫn cần xác minh trên môi trường tương ứng.
