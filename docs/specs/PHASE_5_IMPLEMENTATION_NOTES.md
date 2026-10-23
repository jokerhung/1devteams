# Phase 5 — Workflow Builder

## Phạm vi

- Wizard ba bước: thông tin (tên, prefix gợi ý, mô tả, icon/màu), điểm bắt đầu
  (trống, Fix Bug, Security Review, nhân bản workflow), tạo và mở canvas nháp.
  Kiểm tra tên/prefix trong project, kể cả workflow đã lưu trữ. Project không có
  agent vẫn được tạo nháp; mẫu thiếu vai trò hiển thị cảnh báo và node cần chọn lại.
- Editor React Flow ba cột: palette, canvas chấm có controls/minimap, inspector.
  Agent lấy từ effective agents của project. Agent có quyền Git Release tạo khối
  phát hành. Inspector dùng lại form sửa agent Phase 4 cho quản trị viên.
- Nối dây theo routing, chặn tự nối, vào Start, ra End và trùng source handle.
  Lỗi validator hiển thị dưới canvas, node đỏ; chọn lỗi để focus node.
- Điều kiện dùng đúng ngôn ngữ biểu thức giới hạn của backend: `last_route.<id>`,
  `iteration.<id>`, `len(modified_files)` và phép so sánh; không chạy mã tùy ý.
- Undo/redo bằng Zustand + zundo, lịch sử riêng mỗi editor (100 trạng thái),
  thao tác kéo node được gộp thành một lần hoàn tác. Delete, Ctrl+D, Ctrl+Z/Y,
  Ctrl+Shift+Z, Ctrl+S; không chiếm phím nhập liệu trong inspector.
- Auto-layout Dagre LR, nodesep 60, ranksep 120. Mẫu Security Review đặt review
  giữa developer và tester, fail quay lại developer.
- Lưu cả graph invalid dưới dạng nháp, giữ các trường JSON theo schema API;
  loại metadata React Flow/UI khi serialize. Viewport được lưu cùng graph;
  pan/zoom và selection không làm workflow bị đánh dấu thay đổi nội dung.
- Validate client debounce 300ms; kiểm tra đồng bộ trước bật Xuất bản; lỗi backend
  trả về từ Lưu/Kiểm tra được ưu tiên trên graph đang kiểm tra. Xuất bản cần graph
  đã lưu và hợp lệ, xác nhận version và số ticket đang chạy dùng version cũ.
- Xuất bản lần đầu có nút tạo ticket; chat đầy đủ tiếp tục thuộc Phase 6.
- Pipeline tuyến chính ưu tiên ready/pass/approved/success; nhánh phụ là ghi chú.
  `WorkflowReadonlyGraph` nhận trạng thái từng node cho Phase 6.
- Card dùng chung ở tổng quan và danh sách workflow: sửa thông tin, nhân bản,
  archive/unarchive/xoá theo luật backend. Workflow archived mở editor chỉ đọc.
- Cảnh báo trước khi rời trang, back hoặc reload nếu có nội dung chưa lưu.
  Đăng xuất cũng yêu cầu xác nhận khi đang có thay đổi.

Các loại node dùng chung `nodes/BaseNode.tsx` để đồng nhất khung, trạng thái và
handles; không cần bảy wrapper chỉ chuyển tiếp props. Khi đổi routing, renderer
cập nhật lại hình học handles qua React Flow.

## Backend

`data.max_iterations` là override số vòng lặp của node agent, chấp nhận số nguyên
1–1000. Backend validate khi lưu/xuất bản và runner hỏi người dùng trước lượt vượt
giới hạn, dùng cơ chế gate hiện có. Không truyền override thì dùng cấu hình hệ thống.
Mẫu trống từ API có Start → End; mẫu security của API dùng cùng thứ tự với frontend.
Snapshot đã xuất bản không bị sửa khi lưu graph nháp mới.

## Kiểm chứng

Các lệnh kiểm chứng:

```powershell
cd frontend
npm run lint
npm run typecheck
npm run test
npx playwright test
npm run build
cd ../backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest tests/api tests/engine
```

Playwright chạy SQLite/backend thật và workspace Git riêng ở 3062/8062 theo cấu
hình Phase 4, không dùng database local hoặc dịch vụ provider trả phí. Native ACP
acceptance còn thiếu của Phase 3 giữ nguyên policy gate; Phase 5 không bỏ qua gate.

Đã kiểm chứng:

- Frontend ESLint, TypeScript, production build: đạt.
- Vitest: **21 passed** (serialize, validation, store/history và management).
- Playwright Chromium/backend thật: **4 passed** trong 3 phút, gồm hai ca quản lý,
  luồng Workflow Builder đầy đủ và canvas 30 node.
- Backend Ruff check/format và MyPy: đạt.
- Backend API + engine: **83 passed, 1 deselected** (marker mặc định loại real ACP/API).
- Sau khi đồng bộ mẫu API, chạy lại workflow API + Phase 5 regression:
  **12 passed**, gồm mẫu trống, vị trí security và từ chối publish override sai.

Kiểm thử trình duyệt dùng Chromium/backend thật bao gồm: project trống → thêm
team → wizard → xuất bản → nhân bản → tạo/thêm custom agent → kéo vào canvas,
đổi routing, nối dây → lưu/reload/xuất bản → kiểm tra hai workflow độc lập,
prefix trùng, archive, dirty guard và phím tắt. Ca riêng kiểm tra kéo node,
xoá/undo/redo, nối dây và lưu/reload graph 30 node, kể cả nháp invalid.
