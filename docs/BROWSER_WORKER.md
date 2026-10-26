# Browser Worker

## Sử dụng

1. Chạy `powershell -ExecutionPolicy Bypass -File scripts/setup-browser.ps1` để cài dependency backend
   và Chromium. `scripts/dev.ps1 -Setup` cũng cài Chromium.
2. Vào **Agents & Teams**, sửa agent và bật **Cho phép dùng Browser Worker**.
   `@tester` được bật mặc định; có thể tắt hoặc bật cho bất kỳ agent ACP/API Custom nào.
3. Trong ticket, gửi yêu cầu cho agent, nêu URL, tài khoản test, các bước và tiêu chí thành công.
   Agent dùng công cụ trình duyệt trong cả lượt workflow và chat ad-hoc.

Ví dụ:

> @tester Mở http://10.201.21.211:9090/login?reason=expired, đăng nhập với tài khoản test tôi cung cấp.
> Kiểm tra đã chuyển sang trang có phiên đăng nhập hợp lệ, không còn form đăng nhập.
> Báo PASS/FAIL và screenshot; nếu API lỗi thì ghi mã HTTP thực tế.

Mỗi báo cáo trong chat có trạng thái, tên test case, URL, số kiểm tra, các thao tác và screenshot.
Nhấn screenshot để phóng to. Báo cáo vẫn có khi mở lại chat qua lịch sử tổng hợp.
Các lỗi HTTP quan sát được hiển thị trong phần **Chi tiết kiểm tra**.

## Cách thực thi

Browser Worker chạy Chromium headless trên máy backend. Máy này cần kết nối được tới website.
Không có danh sách URL/domain/IP cho phép hay bị chặn: mọi URL web HTTP/HTTPS, bao gồm LAN,
localhost và Tailscale, đều có thể truy cập. Thiết lập URL của API model là cấu hình riêng.

Runtime được cung cấp giao thức `@@BROWSER` với JSON gồm tối đa 16 thao tác mỗi lần gọi.
Engine thực thi, trả snapshot giao diện cho model, rồi tiếp tục hội thoại tới khi có kết luận.
Cơ chế này dùng được cho cả ACP và API Custom mà không yêu cầu nhà cung cấp hỗ trợ function calling.
API Custom quan sát DOM; runtime ACP hỗ trợ image prompt còn có thể nhận screenshot qua thao tác `screenshot`.

Các thao tác:

- Điều hướng: `navigate`, `snapshot`, `screenshot`.
- Tương tác: `click`, `fill`, `press`, `select`, `check`, `wait_visible`.
- Kiểm tra: `assert_visible`, `assert_hidden`, `assert_text`, `assert_url`, `assert_count`.
- Kết quả: `report`, nhóm thao tác theo `test_case`.

Locator ưu tiên role/tên, label, placeholder, text, test ID; hỗ trợ CSS, iframe và index.
Các thao tác dùng điều kiện chờ của Playwright. Sau thao tác lỗi, engine ngừng batch để agent quan sát lại.

**PASS** cần ít nhất một assertion thực thi thành công và không có thao tác lỗi trong test case.
**FAIL** khi assertion không đạt. **BLOCKED** khi thiếu assertion, lỗi thao tác, lỗi môi trường hoặc bị dừng.
HTTP 200 hoặc click nút không đủ để kết luận đăng nhập thành công.
Nếu báo cáo Browser Worker không đạt, node routing Tester/Review không được đi nhánh `pass`.
Agent có thể đề xuất phân tích bổ sung, nhưng trạng thái trong thẻ báo cáo do worker tính từ kiểm tra thực tế.

## Quyền và dữ liệu

Quyền nằm trong `permission_profile.allow_browser` của mỗi agent; chỉ quản trị viên được đổi qua API agent.
Engine kiểm tra lại quyền trước mỗi thao tác. Tắt quyền có hiệu lực cả với session đã được tạo.
Thiết lập tắt của `@tester` được giữ khi backend khởi động lại.

Mỗi lượt có browser context riêng, không dùng cookie của lượt khác hay profile trình duyệt người vận hành.
Browser đóng khi lượt kết thúc, timeout, hủy hoặc backend dừng. Không lưu cookie hay mật khẩu thành tệp.
Các trường password/`secret:true` được che trong screenshot và giá trị được xóa khỏi snapshot/báo cáo.
Khối lệnh Browser Worker không được ghi vào message chunk hoặc full-text log của chat.
Screenshot dùng hệ thống attachment hiện tại: có thumbnail, quota và quyền đọc theo ticket.
Screenshot được gắn với message báo cáo nên không bị dọn như attachment đang chờ gửi.

## Cấu hình backend/.env

```dotenv
BROWSER_MAX_SESSIONS=4
BROWSER_MAX_ACTIONS=100
BROWSER_MAX_ROUNDS=30
BROWSER_ACTION_TIMEOUT_MS=15000
BROWSER_RUN_TIMEOUT_SEC=900
```

Không cần khai báo URL allowlist. Các giá trị trên điều khiển số phiên, số thao tác/lượt gọi model,
thời gian chờ thao tác và tổng thời gian một lượt có Browser Worker.

## Kiểm chứng

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/engine/test_browser_worker.py -q
```

Kiểm tra dùng Chromium thật với website đăng nhập cô lập; phản hồi model được kiểm soát để xác minh
bridge ACP/API, assertions, screenshot có quyền truy cập, lịch sử chat, quyền agent và dọn phiên.
