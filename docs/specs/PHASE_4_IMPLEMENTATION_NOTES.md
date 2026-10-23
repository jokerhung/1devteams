# Phase 4 — Frontend shell và quản lý

## Phạm vi triển khai

- Shell Next.js theo mockup `docs/aiTeams_gui.html`: nền kem, panel trắng bo góc,
  Inter/JetBrains Mono, sidebar 240px, drawer dưới 1024px.
- Đăng nhập qua Next route handler; JWT nằm trong cookie httpOnly, SameSite=Lax.
  API và ảnh đi qua proxy cùng origin, lỗi backend được hiển thị bằng tiếng Việt.
  Các thao tác ghi kiểm tra Origin; middleware bảo vệ các trang workspace.
- Trang Agents & Teams: tạo/sửa/xoá, built-in chỉ có nút sửa; logo emoji/upload,
  model catalog, preset và quyền chi tiết, tag lệnh cho phép/cấm, kiểm tra kết nối,
  usage và trạng thái restart. Sửa không thay đổi cấu hình không gọi PATCH/restart;
  thay đổi team riêng không restart agent. API key để trống khi sửa được giữ nguyên.
- OpenAI Custom: Base URL, key mật khẩu, model tự do và gợi ý từ kiểm tra kết nối;
  không cho quyền ghi/terminal/release. Không trả JWT hoặc API key đã lưu về browser.
- Projects: tạo project trống với đúng ba trường, kiểm tra workspace, tổng quan,
  settings, xoá project, thành viên người dùng/team/agent, agent hiệu lực.
- Sidebar: sắp theo last_activity_at, top 5 có ghim project hiện tại, trạng thái mở
  riêng từng project/workflow trong localStorage, modal tất cả project, lazy tree.
- Workflow: tổng quan và danh sách ticket, tạo từ mẫu rồi xuất bản để kiểm tra luồng
  quản lý; chỉ workflow PUBLISHED có nút tạo ticket. Tệp đính kèm được upload trước
  khi start để prompt đầu có đủ tệp; lỗi upload có thể tiếp tục trên ticket đã tạo.
- Thông báo: cần xử lý/đã xử lý, số đếm, đánh dấu đọc, lịch sử outcome, phân trang.
  Backend quyết định resolve; frontend invalidate sau sự kiện realtime.
- Route `/teams` redirect 308 về `/agents`. Canvas là placeholder Phase 5;
  cửa sổ chat là placeholder Phase 6 như phạm vi Phase 4.

## Data và realtime

Types được sinh từ OpenAPI tại `frontend/src/lib/api/schema.d.ts`, dùng chung trong
các trang. TanStack Query quản lý cache/mutation và invalidation.

Browser dùng EventSource `/api/events`; Next server mở WebSocket thật tới backend
`/ws/users/me` và `/ws/projects/{id}` với Authorization header. Cầu nối này giữ JWT
trong cookie httpOnly và không đưa token vào URL hay JavaScript phía client.
Hỗ trợ envelope project, ping/pong, tự reconnect và refetch khi kết nối lại.
Server Next cần hỗ trợ response streaming và WebSocket outbound.

API bổ sung:

- `PATCH /api/projects/{id}/members/USER/{user_id}` đổi project_role tại chỗ.
- Gỡ thành viên/team, thay danh sách agent của team hoặc xoá team trả 409 nếu làm
  mất agent cần cho graph nháp hoặc snapshot đã xuất bản của workflow chưa archived.
  Lỗi liệt kê workflow cần sửa; transaction bị rollback khi từ chối.
- Upload ảnh PNG hỏng checksum trả 422 thay vì 500; kiểm tra hồi quy dùng ảnh
  nhận diện đúng định dạng nhưng hỏng chunk dữ liệu.
- Người dùng MAINTAINER không có system role quản trị nhập UUID để thêm người dùng;
  danh sách `/users` vẫn giữ phân quyền quản trị của backend.

## Chạy và kiểm chứng

```powershell
.\scripts\dev.ps1
cd frontend
npm run gen:api
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npx playwright test
```

`BACKEND_URL` là địa chỉ server-side, mặc định fallback về `NEXT_PUBLIC_API_URL`,
sau đó `http://127.0.0.1:8060`. `OPENAPI_URL` có thể đổi riêng URL sinh types.
Không cần frontend giữ JWT trong localStorage.

Playwright tự chạy backend trên 8062 và frontend trên 3062, dùng SQLite mới và Git
workspace riêng dưới `frontend/.e2e-data/`. Không đọc database local của ứng dụng,
không dừng các dịch vụ dev trên 3060/8060. `E2E_PYTHON` cho phép chọn Python khác.
`NEXT_DIST_DIR=.next-e2e` tách output khỏi dev; khi build song song có thể đặt
`NEXT_DIST_DIR=.next-build`. Artifact, DB và screenshot test được gitignore.

### Kết quả xác minh (23/10/2026)

- Vitest: **10/10** test đạt (AgentForm, LogoPicker, TeamForm, Sidebar, thông báo).
- Backend API: **41/41** test đạt; chạy lại 2 test attachment/logo sau sửa checksum:
  **2/2** đạt.
- Backend Ruff check, Ruff format và MyPy đạt.
- Frontend ESLint và TypeScript (`npm run typecheck`) đạt.
- Production build (`NEXT_DIST_DIR=.next-build npm run build`) đạt.
- Playwright Chromium: **2/2** kịch bản E2E đạt với backend thật, gồm xác minh
  số project sử dụng team sau cập nhật cache.
- Đã xem screenshot trang Agents & Teams và project trên viewport 1440 × 1000,
  đối chiếu mockup; Playwright kiểm tra drawer ở 900 × 800.
- Browser E2E dùng backend thật: tạo/sửa agent và badge restart, tạo team, chặn team
  rỗng, project trống, member/role, workflow nháp/xuất bản, ticket/chat URL, bảo vệ
  membership 409, thứ tự/ghim/sidebar tree, upload/đọc logo, xoá entity, CSRF và logout.
  Số project sử dụng team được kiểm tra sau thay đổi membership để tránh cache cũ.

Native ACP acceptance còn thiếu của Phase 3 không bị thay đổi hoặc bỏ qua bởi
Phase 4; E2E quản lý tạo ticket ở chế độ “Chỉ tạo, chưa chạy” để kiểm chứng độc
lập với provider. Các test kết nối OpenAI Custom trong Vitest dùng API giả lập;
không gọi dịch vụ trả phí. Canvas và chat đầy đủ vẫn thuộc Phase 5–6.
