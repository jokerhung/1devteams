# Cài đặt 1devTeams từ đầu

Không cần cài sẵn Python, Node.js, uv hay Git; không cần clone hoặc giải nén
source thủ công. Bootstrap ở thư mục gốc tải source rồi gọi bộ cài tương ứng
trong `scripts/install/`. Cần Internet, dung lượng cho dependency/browser và
quyền cài các gói hệ điều hành. Đọc script từ URL trước khi cho phép thực thi.

## Một lệnh từ máy mới

Windows (mở PowerShell):

```powershell
irm https://raw.githubusercontent.com/jokerhung/aiTeams/main/install.ps1 | iex
```

Linux hoặc macOS (mở terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/jokerhung/aiTeams/main/install.sh | bash
```

Windows mặc định cài vào `%LOCALAPPDATA%\1devTeams`; Linux/macOS vào
`$HOME/1devTeams`. Dùng biến môi trường `ONEDEVTEAMS_INSTALL_DIR` (đường dẫn
tuyệt đối) để chọn thư mục khác. Bootstrap từ chối thư mục đã tồn tại,
không ghi đè source/config/dữ liệu; nếu cài lỗi, source được giữ lại để chạy
lại bộ cài bên dưới. Thư mục tải tạm được dọn sau khi tải/giải nén.

URL dùng nhánh `main` của `jokerhung/aiTeams`: cần **push toàn bộ bộ cài lên
GitHub và repository phải truy cập công khai** trước khi phân phối lệnh này.
Không có credential GitHub trong script. Máy Linux tối giản cần có `curl`,
`tar`, `bash` và `sudo`; ví dụ cài curl nếu thiếu: `sudo apt-get update &&
sudo apt-get install -y curl`. macOS có sẵn các công cụ tải/giải nén.

Đây là một lệnh khởi động toàn bộ quy trình cài, không phải chế độ hoàn toàn
không tương tác: OS có thể hỏi quyền/mật khẩu sudo hoặc mở hộp thoại Apple;
đăng nhập tài khoản AI vẫn do người dùng thực hiện sau khi cài.

## Cài từ source / chạy lại

Nếu đã có source, mở terminal tại thư mục chứa `backend/`, `frontend/` rồi
dùng một trong các lệnh sau. Đây cũng là cách truyền các tùy chọn chi tiết.

Windows 10/11, PowerShell 5.1 trở lên:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install/windows.ps1 -AdminEmail you@example.com
```

Git được cài bằng WinGet nếu thiếu; script thử khôi phục WinGet bằng module
Microsoft chính thức nếu chưa có. Chấp nhận hộp thoại cấp quyền khi Windows yêu
cầu. Máy bị chính sách doanh nghiệp chặn WinGet/PowerShell Gallery cần quản trị
viên hỗ trợ; không tắt chính sách bảo mật toàn máy.

Linux — Ubuntu 22.04/24.04 hoặc Debian 12/13, x64/ARM64:

```bash
bash scripts/install/linux.sh --admin-email you@example.com
```

Chạy bằng user thường có quyền `sudo`, không chạy cả script bằng root. Script
cài dependency bằng `apt-get`; Playwright cũng có thể yêu cầu mật khẩu sudo.
Các distro khác chưa có quy trình tự động trong bộ cài này.

macOS — Intel hoặc Apple Silicon, dùng bản macOS còn được Playwright hỗ trợ:

```bash
bash scripts/install/macos.sh --admin-email you@example.com
```

Không cần Homebrew. Nếu thiếu Apple Command Line Tools, hoàn tất hộp thoại cài
đặt của Apple rồi nhấn Enter trong terminal. Không chạy bằng `sudo`.

## Bộ cài thực hiện gì?

1. Chuẩn bị Git, uv và Python 3.12; dùng Node.js có sẵn nếu từ 22 trở lên,
   nếu không tải Node.js 22 vào `.tools/node` và kiểm tra SHA-256.
2. Cài backend theo `uv.lock`, ACP adapters và frontend theo npm lockfile;
   cài Claude Code/Codex CLI cục bộ vào `.tools/providers` và Chromium cho
   Browser Worker. Các provider CLI lấy phiên bản hiện tại khi cài.
3. Tạo `.env`, `backend/.env`, `frontend/.env` nếu chưa có; sinh ngẫu nhiên
   JWT secret, khóa mã hóa Fernet và mật khẩu Owner. Không in mật khẩu ra log.
4. Migrate SQLite tại `backend/data/aiteams.db`, tạo dữ liệu mẫu, build frontend.
   File cấu hình mới chỉ cấp quyền đọc/ghi cho tài khoản cài đặt.

Dữ liệu sẵn có trên cài đặt mới:

- **1 Owner**: email đã chọn, mặc định `owner@example.com`.
- **9 agents**: `@ba`, `@developer`, `@tester`, `@devops`, `@leader`, `@planner`,
  `@designer`, `@workflow`, `@security`.
- **3 teams**: Core Bugfix Squad, Feature Delivery Squad, Security Review Squad.
- **4 workflow templates**: Blank (`blank`), Fix Bug (`bugfix_default`),
  Add Feature (`add_feature`), Fix Bug + Security Review (`bugfix_with_security_review`).

Templates được lưu vào database và gắn đúng agent; bước Git release vẫn yêu cầu
người dùng xác nhận. Bộ cài không tự tạo project/ticket hoặc chạy agent.

## Khởi chạy và đăng nhập

Windows:

```powershell
.\backend\.venv\Scripts\python.exe scripts/install/run.py
```

Linux/macOS:

```bash
./backend/.venv/bin/python scripts/install/run.py
```

Truy cập `http://localhost:3060`. Lấy email/mật khẩu Owner tại
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` trong `backend/.env`.
Không chia sẻ hoặc commit file này. Đổi mật khẩu sau khi đăng nhập.

Launcher tự mở trình duyệt sau khi hai dịch vụ sẵn sàng. Dùng `--no-open` để
không mở browser; `--check` để khởi động, kiểm tra HTTP rồi dừng. Ctrl+C dừng
cả hai dịch vụ; log tại `.dev-logs/installed-*.log`. Đây là launcher chạy ở
foreground, **không tự đăng ký Windows Service/systemd/launchd hoặc tự chạy
khi bật máy**.

Vào **Settings → Adapters → Login** để đăng nhập Claude/Codex bằng tài khoản
của bạn. Cài binary và tạo agents không đồng nghĩa đã có quyền sử dụng dịch vụ
AI; bộ cài không cung cấp tài khoản, API key hoặc gói dịch vụ của nhà cung cấp.
Nếu đã bỏ qua cài provider, cần cài chúng trước khi Login.

## Tùy chọn

| PowerShell | Linux/macOS | Ý nghĩa |
| --- | --- | --- |
| `-AdminEmail EMAIL` | `--admin-email EMAIL` | Email Owner khi tạo mới |
| `-Workspace PATH` | `--workspace PATH` | Thư mục được phép truy cập, mặc định `<repo>/workspaces` |
| `-FrontendPort 3060` | `--frontend-port 3060` | Cổng web |
| `-BackendPort 8060` | `--backend-port 8060` | Cổng backend |
| `-PublicUrl URL` | `--public-url URL` | Thêm origin truy cập từ LAN/domain vào CORS |
| `-TrustNativeAgents` | `--trust-native-agents` | Cho phép native Claude/Codex chạy với quyền OS user |
| `-EnableRemoteTerminal` | `--enable-remote-terminal` | Cho phép terminal từ web |
| `-SkipProviders` | `--skip-providers` | Không cài Claude Code/Codex CLI |
| `-SkipBrowser` | `--skip-browser` | Không cài Chromium/dependency browser |
| `-Help` | `--help` | Xem cách dùng |

Mặc định native agents và remote terminal **bị tắt**. Chỉ bật khi tin cậy
workspace và người sử dụng: native tools có quyền của tài khoản hệ điều hành,
không được sandbox bởi permission profile trong giao diện. Có thể bật sau
bằng `TRUSTED_NATIVE_ACP=true` / `ENABLE_REMOTE_TERMINAL=true` trong
`backend/.env`, rồi khởi động lại. Nếu bỏ qua Chromium, Browser Worker sẽ
không sẵn sàng cho đến khi cài browser.

Ví dụ cài máy nội bộ đã tin cậy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install/windows.ps1 -AdminEmail you@example.com -Workspace D:\projects -PublicUrl http://192.168.1.10:3060 -TrustNativeAgents
```

`--public-url` chỉ cấu hình CORS, không thiết lập DNS/TLS/firewall. Web lắng
nghe trên `0.0.0.0`, backend chỉ trên loopback. Không mở trực tiếp ra Internet;
khi triển khai từ xa cần HTTPS, reverse proxy hỗ trợ WebSocket và kiểm soát
truy cập phù hợp.

## Chạy lại / xử lý lỗi

- Dừng ứng dụng trước khi cài lại. Bộ cài từ chối nếu cổng web/backend đang
  được sử dụng; nó không tự kill tiến trình đang chạy.
- File `.env` đã tồn tại được giữ nguyên, kể cả khi truyền tùy chọn khác.
  Muốn đổi email/cổng/quyền/workspace trên cài đặt cũ, sửa cấu hình tương ứng;
  các tùy chọn không reset mật khẩu của Owner đã có.
- Dữ liệu mẫu chỉ được thêm nếu thiếu theo handle/tên/key; không xóa dữ liệu
  người dùng hoặc ghi đè template đã chỉnh. Migration và seed tương thích
  của ứng dụng vẫn được áp dụng. Đây không phải công cụ reset/restore.
- Sao lưu database, attachments và các file `.env` trước khi nâng cấp.
  Không xóa `.env` để chữa lỗi: mất `APP_SECRET_KEY` có thể làm credential đã
  mã hóa không đọc được. Cấu hình mẫu chưa sửa secret/mật khẩu sẽ bị từ chối.
- Khi đổi cổng, sửa `.env` gốc, URL trong `frontend/.env` và CORS trong
  `backend/.env`, rồi chạy lại bộ cài để build rewrite WebSocket theo cổng mới.
- Nếu tải/cài gói bị lỗi mạng, xử lý thông báo rồi chạy lại cùng lệnh. Cài đặt
  không có rollback tự động, nhưng có thể tiếp tục trên cấu hình đã tạo.
- `.tools`, workspace mặc định, database, `.env`, logs và build output đều
  được loại khỏi Git. Không sao chép `.venv`/`.tools` giữa các hệ điều hành;
  chạy bộ cài riêng trên từng máy.

## Kiểm chứng

Kiểm tra syntax PowerShell/Bash, lint Python và kiểm tra migration/seed trên
SQLite tạm (tạo mới, chạy lại, bảo toàn cấu hình, bind agent cho template):

```powershell
.\backend\.venv\Scripts\python.exe -m pytest scripts/install/tests -q
.\backend\.venv\Scripts\python.exe -m ruff check --config backend/pyproject.toml scripts/install
```

Các kiểm tra này không cài gói hệ thống, không gọi provider AI và không thay
database đang dùng. Chưa xác nhận một lần cài end-to-end trên máy sạch cho
từng hệ điều hành; Linux/macOS vẫn cần kiểm thử native trước khi phát hành.

Nguồn tải và yêu cầu nền tảng:
[uv](https://docs.astral.sh/uv/getting-started/installation/),
[Node.js 22](https://nodejs.org/download/release/latest-v22.x/),
[WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/),
[Playwright](https://playwright.dev/python/docs/intro#system-requirements).
