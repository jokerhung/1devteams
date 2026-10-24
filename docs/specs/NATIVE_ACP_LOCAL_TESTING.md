# Chạy native ACP trên máy test

Mặc định `TRUSTED_NATIVE_ACP=false`. Claude/Codex native bị khóa vì chưa xác minh
toàn bộ công cụ native đi qua permission guard. Đây không phải lỗi kết nối model.

Nếu người vận hành chấp nhận quyền của adapter trên máy test, đặt trong `backend/.env`:

```dotenv
TRUSTED_NATIVE_ACP=true
```

Khởi động lại backend rồi chạy lại ticket lỗi. Tùy chọn này chỉ được đọc từ cấu hình
máy chủ; biến môi trường của từng agent không thể bật nó.

Ở chế độ tin cậy, công cụ native có thể thực thi trực tiếp với quyền tài khoản hệ
điều hành. Permission profile không bảo đảm kiểm soát toàn bộ công cụ native.
Guard vẫn kiểm tra đường dẫn, quyền terminal và danh sách lệnh của các yêu cầu qua ACP client.
Nếu agent được phép terminal và không có allowlist, chế độ tin cậy cho phép shell expansion,
redirection, heredoc và interpreter. Chặn lệnh Git thay đổi dữ liệu và các lệnh trong
blocklist chỉ là kiểm tra best-effort với chuỗi lệnh; không bảo đảm bắt được lệnh
được che giấu trong script hay biến shell. Allowlist vẫn dùng kiểm tra nghiêm ngặt.
Không coi chế độ này là sandbox
hay bằng chứng hoàn tất acceptance về cách ly công cụ. Mỗi lượt agent có thông báo
`runtime_policy=trusted_native` trong log ticket.

Đặt lại `TRUSTED_NATIVE_ACP=false` và khởi động lại backend để trở về chế độ khóa
mặc định. `ENABLE_REMOTE_TERMINAL` là cấu hình terminal của người dùng, độc lập với
chính sách native ACP.

## Provider bị trỏ tới proxy tạm

Nếu backend chạy từ IDE/agent có gateway tạm, đặt `ACP_INHERIT_PROVIDER_ENV=false`
trong `backend/.env` rồi khởi động lại backend. Native adapter không kế thừa các biến
`ANTHROPIC_*`, `OPENAI_*`, `CODEX_API_KEY`, `CODEX_CONFIG`, `MODEL_PROVIDER`,
`DEFAULT_AUTH_REQUEST` từ process cha. Claude/Codex sử dụng cấu hình và đăng nhập CLI
của tài khoản chạy backend. Có thể cấu hình provider riêng bằng các biến tương ứng
trong `backend/.env`; chúng vẫn được truyền vào adapter. Không thay đổi cấu hình
provider của IDE hoặc tài khoản hệ điều hành.
