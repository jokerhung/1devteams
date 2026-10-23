# Phase 6 — Ticket Chat Runtime

## Đã triển khai

- Thay trang ticket tạm bằng channel: lịch sử phẳng, gom lượt theo `run_id`, thinking,
  markdown GFM/Shiki, tool chips, diff tổng hợp/unified/split, terminal và permission denial.
- Log ngay dưới tên từng agent, thu gọn dòng cuối, mở toàn bộ log có bộ lọc, copy và phân trang.
- BA hỏi lại, confirm/reject inline với feedback bắt buộc trên UI, lịch sử người duyệt,
  thông báo focus gate, trạng thái readonly khi ticket kết thúc.
- Composer có mention autocomplete, mặc định lưu server/localStorage qua ticket/project;
  chọn file, kéo thả, dán ảnh, progress, gỡ tệp pending, ảnh phóng to và tải tệp.
  Giới hạn lấy từ backend (`ATTACH_MAX_FILES`, `ATTACH_MAX_MB`).
- Bản nháp tệp/text tách theo user và ticket, giữ khi điều hướng SPA; không lưu blob qua reload.
- Tin nhắn optimistic có retry và `client_msg_id`; backend trả lại tin đã lưu khi gửi lại cùng ID.
- Store khử trùng seq, resume từ seq liên tục, bảo vệ snapshot mới khỏi lịch sử cũ.
  Virtualize trên 300 group, markdown đang stream cập nhật mỗi 200 ms.
- Drawer hiển thị graph đúng workflow version của ticket và timeline; Terminal dành Phase 7.
- Kết quả Git có hash copy, branch, file và số dòng thay đổi. Git vẫn do backend thực hiện.
- Ticket mới có tin nhắn user ban đầu được lưu; attachment đưa đường dẫn vào prompt tiếp theo
  và loại khỏi Git qua `.git/info/exclude`.

## Transport và quyền

`TicketSocket` dùng SSE cùng origin của Next, route server giữ WebSocket tới backend,
trả ping/pong và chuyển `after_seq`. JWT httpOnly không được đưa xuống browser.
Backoff 1/2/5/10 giây, đóng transport khi đổi ticket. Các kênh sidebar dùng chung một
SSE trong mỗi tab để thao tác REST không bị chặn bởi giới hạn kết nối HTTP khi mở hai tab.
Backend kiểm tra quyền report/confirm và trạng thái kết thúc; `/chat-config` chỉ cung cấp
quyền và giới hạn cho UI. Xóa attachment chỉ cho phép chủ sở hữu xóa tệp chưa gắn tin nhắn.

## Kiểm chứng

- Backend API + engine với SQLite: **87 passed, 1 deselected** (native opt-in).
- Frontend unit: fixture JSON xuất trực tiếp từ engine kiểm chứng grouping, diff tổng,
  gate gắn tester, dedup/resume/snapshot và optimistic acknowledgement.
- Frontend unit: **29 passed**. Lint, typecheck: đạt.
- Production build Next.js: đạt. Backend Ruff lint/format và mypy: đạt.
- Playwright toàn bộ: **5 passed**, gồm 2 management, 2 workflow builder và 1 chat runtime.
  Luồng chat kiểm tra tạo auto-start → BA hỏi lại → tệp/mention → guard/diff → reject
  → tester chạy lại → confirm hai tab → commit/push remote bare → completed readonly,
  preference qua project/reload và drawer snapshot.
- Git/commit URL regression: **7 passed**; handler/WebSocket regression: **7 passed**.
  Link GitHub/GitLab chỉ tạo từ remote hợp lệ, bỏ thông tin đăng nhập khỏi URL.
- Playwright `e2e/ticket.spec.ts` chạy provider giả chỉ trong test; dùng DB/checkpoint,
  workspace và remote bare riêng trong `.e2e-data`, cổng 3062/8062.
  Không nhập provider giả vào production và không bỏ native policy gate.

Lệnh:

```powershell
cd backend
.venv/Scripts/python.exe -m pytest tests/api tests/engine -q -k "not native"
.venv/Scripts/python.exe -m ruff check app tests
.venv/Scripts/python.exe -m mypy app
cd ../frontend
npm test
npm run lint
npm run typecheck
npx playwright test
npm run build
```

## Acceptance còn phụ thuộc

Native E2E Claude/Codex trên bản copy `HNBG_DEV` vẫn bị policy gate Phase 3 chặn:
adapter chưa được xác minh tool mediation/client-only routing hoặc sandbox tương ứng.
Không đánh dấu đạt native acceptance bằng kết quả provider giả. Xem
[ghi chú Phase 3](PHASE_3_IMPLEMENTATION_NOTES.md).

Chu kỳ render markdown 200 ms chưa chứng minh độ trễ từ backend nhận chunk tới pixel
luôn dưới 300 ms; cần đo end-to-end trong môi trường triển khai. Hai mục này giữ mở
trong Definition of Done của spec.
