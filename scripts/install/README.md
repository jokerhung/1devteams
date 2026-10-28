# Cài đặt 1devTeams từ đầu

Không cần cài sẵn Python, Node.js, uv hay Git; không cần clone hoặc giải nén
source thủ công. Bootstrap ở thư mục gốc tải source rồi gọi bộ cài tương ứng
trong `scripts/install/`. Cần Internet, dung lượng cho dependency/browser và
quyền cài các gói hệ điều hành. Đọc script từ URL trước khi cho phép thực thi.

## Một lệnh từ máy mới

Windows (mở PowerShell):

```powershell
irm https://raw.githubusercontent.com/jokerhung/1devteams/main/install.ps1 | iex
```

Linux hoặc macOS (mở terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/jokerhung/1devteams/main/install.sh | bash
```

Windows mặc định cài vào `%LOCALAPPDATA%\1devTeams`; Linux/macOS vào
`$HOME/1devTeams`. Dùng biến môi trường `ONEDEVTEAMS_INSTALL_DIR` (đường dẫn
tuyệt đối) để chọn thư mục khác. Nếu thư mục chứa bản đã cài hoàn chỉnh,
chạy lại cùng lệnh sẽ **chạy ngay bản đang có** bằng Python trong
`backend/.venv`; không cập nhật source ứng dụng hay cài dependency lại.
Bootstrap tải riêng nội dung launcher mới nhất từ
`scripts/install/run.py` trên GitHub vào bộ nhớ, chạy với thư mục gốc của bản
đã cài để in URL localhost/IP và cấu hình CORS cho IP mạng. Không ghi đè file
launcher trên máy. Link chỉ được in sau khi web sẵn sàng.
Source/config/dữ liệu không bị ghi đè; database vẫn được ứng dụng sử dụng
bình thường khi khởi động. Đây không phải lệnh nâng cấp lên bản mới.

Nếu thư mục chưa cài xong (thiếu venv, runtime config, frontend build hoặc
cấu hình `.env`), bootstrap báo file thiếu và cách chạy bộ cài bên dưới.
Thư mục không liên quan cũng không bị ghi đè. Nếu cài lỗi, source được giữ
lại để tiếp tục cài; thư mục tải tạm được dọn sau khi tải/giải nén.

URL dùng nhánh `main` của `jokerhung/1devteams`: cần **push toàn bộ bộ cài lên
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
2. Tạo virtual environment riêng `backend/.venv` bằng uv và cài backend theo
   `uv.lock` vào đó, không cài Python package toàn hệ thống. Bộ cài luôn dùng
   venv này kể cả khi shell đặt `UV_PROJECT_ENVIRONMENT` trỏ nơi khác.
   Cài ACP adapters và frontend theo npm lockfile;
   cài Claude Code/Codex CLI cục bộ vào `.tools/providers` và Chromium cho
   Browser Worker. Các provider CLI lấy phiên bản hiện tại khi cài.
3. Tạo `.env`, `backend/.env`, `frontend/.env` nếu chưa có; sinh
   JWT secret và khóa mã hóa Fernet ngẫu nhiên; đặt mật khẩu Owner mặc định
   `123456`. Database lưu hash của mật khẩu, không lưu mật khẩu thuần.
4. Migrate SQLite tại `backend/data/aiteams.db`, tạo dữ liệu mẫu, build frontend.
   File cấu hình mới chỉ cấp quyền đọc/ghi cho tài khoản cài đặt.
5. Tự khởi động backend/frontend; sau khi health check thành công, in URL
   localhost và các IP mạng cục bộ để truy cập. Giữ terminal mở để web chạy;
   Ctrl+C dừng cả hai dịch vụ. Dùng `-NoStart` / `--no-start` để bỏ bước này.

Dữ liệu sẵn có trên cài đặt mới:

- **1 Owner**: email đã chọn, mặc định `owner@example.com`; mật khẩu `123456`.
- **9 agents**: `@ba`, `@developer`, `@tester`, `@devops`, `@leader`, `@planner`,
  `@designer`, `@workflow`, `@security`.
- **3 teams**: Core Bugfix Squad, Feature Delivery Squad, Security Review Squad.
- **4 workflow templates**: Blank (`blank`), Fix Bug (`bugfix_default`),
  Add Feature (`add_feature`), Fix Bug + Security Review (`bugfix_with_security_review`).

Templates được lưu vào database và gắn đúng agent; bước Git release vẫn yêu cầu
người dùng xác nhận. Bộ cài không tự tạo project/ticket hoặc chạy agent.

## Khởi chạy và đăng nhập

Bộ cài tự khởi động web sau khi hoàn tất. Terminal sẽ hiển thị, ví dụ:

```text
1devTeams is ready.
  Localhost: http://localhost:3060
  Network:   http://192.168.1.20:3060
```

IP/cổng phụ thuộc cấu hình thực tế. Khi có nhiều IP LAN/VPN, launcher có thể
in nhiều link. Nếu không phát hiện IP phù hợp, localhost vẫn được in và có
thông báo không phát hiện IP. Link chỉ xuất hiện sau khi backend và frontend
sẵn sàng; lỗi khởi động chỉ tới log để chẩn đoán, không báo thành công giả.

Để khởi động lại sau khi đã dừng, chạy từ thư mục source:

Windows:

```powershell
.\backend\.venv\Scripts\python.exe scripts/install/run.py
```

Linux/macOS:

```bash
./backend/.venv/bin/python scripts/install/run.py
```

Truy cập `http://localhost:3060`. Đăng nhập mặc định: **`owner@example.com` / `123456`**.
Email/mật khẩu khởi tạo được lưu tại
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` trong `backend/.env`.
Không chia sẻ hoặc commit file này. **Đổi mật khẩu ngay sau khi đăng nhập và
trước khi mở truy cập qua mạng**: `123456` là mật khẩu công khai, không an toàn
để dùng lâu dài. Mật khẩu mới phải có ít nhất 8 ký tự. Chạy lại bộ cài không
reset mật khẩu đã đổi hoặc tài khoản đã có.

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
| `-NoStart` | `--no-start` | Chỉ cài/build, không tự khởi động web |
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
nghe trên `0.0.0.0`, backend chỉ trên loopback. Launcher tự thêm localhost và
các IPv4 mạng cục bộ phát hiện được vào CORS trong môi trường tiến trình,
không sửa `.env`, không xóa origin riêng và không dùng wildcard. Việc này giúp
chat/terminal qua IP không bị chặn Origin; quyền agent/terminal vẫn giữ nguyên.
Máy khách phải truy cập được LAN/VPN của máy chủ và firewall phải cho phép
cổng frontend. Không tự mở port hoặc tạo public URL. Không mở trực tiếp ra Internet;
khi triển khai từ xa cần HTTPS, reverse proxy hỗ trợ WebSocket và kiểm soát
truy cập phù hợp.

## Chạy lại / xử lý lỗi

- Nếu thấy `getcwd() failed` / `Current directory does not exist`, shell đang
  đứng trong thư mục đã bị xóa. Chạy `cd "$HOME"` rồi gọi lại bootstrap, hoặc
  `cd "$HOME/1devTeams"` và chạy `bash scripts/install/linux.sh` để tiếp tục
  cài dở trên Linux. Bộ cài mới tự chuyển vào thư mục hợp lệ trước khi gọi uv.
- Chạy lại lệnh bootstrap một dòng trên bản đã cài sẽ chỉ khởi động bản đó.
  Nếu ứng dụng đang chạy trong terminal khác, dùng URL tại đó; launcher không
  kill tiến trình hoặc tạo bản thứ hai trên cổng đang bận. Nếu không tải được
  startup helper, có cảnh báo trước khi dùng launcher trên máy; launcher cũ
  có thể chỉ in localhost. Khi đó kiểm tra mạng rồi chạy lại bootstrap.
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
