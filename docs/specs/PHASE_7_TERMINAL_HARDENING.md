# PHASE 7 — Remote Terminal (PTY + xterm), Model Fallback, Vận hành & Hardening

## 1. Mục tiêu
1. **Remote Terminal** kiểu 9remote: tab Terminal trong RightDrawer, gõ lệnh trực tiếp trên workspace (cho Developer/Leader can thiệp thủ công, chạy `claude /login`, xem `git log`).
2. **Model fallback & retry** khi gặp lỗi quá tải (“Selected model is at capacity”, HTTP 429/529).
3. **Ad-hoc mention**: gõ `@agent` khi ticket không ở trạng thái chờ → agent đó trả lời một lượt ngoài workflow (giống Buzz).
4. Audit log, giới hạn tài nguyên, bảo mật, đóng gói chạy trên Windows.

## 2. Remote Terminal

### 2.1. Backend `app/acp/pty_manager.py` + `app/ws/terminal_ws.py`
- Windows: `pywinpty` (`winpty.PtyProcess.spawn("powershell.exe -NoLogo", cwd=workspace, dimensions=(rows, cols))`); Linux/macOS: `ptyprocess`.
- `WS /ws/terminal/{project_id}?token=...`:
  - Client → server: `{"type":"input","data":"..."}`, `{"type":"resize","cols":120,"rows":30}`.
  - Server → client: raw output dạng `{"type":"output","data":"..."}` (đọc PTY trong thread executor, đẩy qua `asyncio.Queue`).
- Quyền: chỉ user `MAINTAINER` của project; tắt toàn cục bằng `ENABLE_REMOTE_TERMINAL=false`.
- Mỗi user/project tối đa 1 PTY; đóng khi WS ngắt > 10 phút (giữ phiên để reconnect).
- Ghi audit: thời điểm mở/đóng, user, (tùy chọn) toàn bộ input lệnh vào `terminal_audit`.
- Cảnh báo UI: terminal này **không** đi qua Permission Guard — đây là quyền của con người.

### 2.2. Frontend `RemoteTerminal.tsx`
- `@xterm/xterm` + `@xterm/addon-fit` + `@xterm/addon-web-links`; theme tối (nền `#0c0a09`), font JetBrains Mono 12px.
- Load bằng `dynamic(() => import(...), { ssr: false })`.
- ResizeObserver → fit → gửi `resize`.
- Thanh công cụ: Kết nối lại, Xoá màn hình, Copy, nút lệnh nhanh (`git status`, `git log --oneline -10`, `npm test`).

## 3. Model fallback & retry
- Thêm vào agent: `fallback_model` (đã có cột Phase 2) và cho phép `fallback_runtime` (VD Claude quá tải → chuyển Codex, hoặc **chuyển sang agent `openai-api`** cho các vai trò text-only như BA/review) — tùy chọn, mặc định tắt. Không cho fallback sang `openai-api` với agent cần ghi file/chạy lệnh.
- Với `openai-api`: tôn trọng header `Retry-After` của 429; 401/404 **không retry** (lỗi cấu hình) mà tạo thông báo/`error` rõ ràng; ghi `usage` (token vào/ra) vào `metadata` của `agent_turn_end` để sau này thống kê chi phí.
- Phát hiện lỗi quá tải: stopReason/error message chứa `capacity`, `overloaded`, `429`, `529`, `rate limit` (danh sách cấu hình trong `config`).
- Chính sách (`engine/retry.py`): retry cùng model sau 30s → 60s (tối đa 2 lần) → chuyển `fallback_model` (tạo session mới, gửi lại prompt đầy đủ của lượt) → nếu vẫn lỗi: `human_input` gate “@developer không chạy được do model quá tải. Thử lại / đổi model / huỷ”.
- Mỗi lần chuyển: event `SYSTEM` “⚠ @developer chuyển sang model `<fallback>` do model chính quá tải”.
- Gợi ý phân tải (từ tài liệu): BA/Tester dùng model nhanh, Developer/Leader dùng model mạnh — đưa vào preset khi seed.

## 4. Ad-hoc mention (ngoài workflow)
- Mention thường được client tự thêm từ **agent mặc định của nút @** (Phase 6 §5.7) nên backend phải coi mọi tin nhắn không phải reply/confirm là ad-hoc nếu có mention hợp lệ; tin nhắn có thể kèm file đính kèm (đưa vào prompt như Phase 3 §11.3).
- `POST /tickets/{id}/messages` có mention `@x` và ticket không ở `WAITING_*`/`RUNNING` hoặc agent x không phải node hiện tại → tạo **ad-hoc turn**: dùng session của agent trong ticket (pool), prompt = ngữ cảnh ticket + tin nhắn user; chạy với permission profile của agent đó; **không** thay đổi trạng thái workflow.
- Không cho ad-hoc với `@leader` để commit — leader ad-hoc chỉ trả lời (git_release chỉ chạy trong workflow).
- Hàng đợi: nếu workflow đang RUNNING → ad-hoc xếp hàng sau lượt hiện tại (hoặc từ chối nếu agent đang bận).

## 5. Vận hành & bảo mật
| Hạng mục | Việc cần làm |
|---------|--------------|
| Huỷ/dừng | Nút “Dừng agent” trong AgentTurn → `session/cancel`; Huỷ ticket → cancel toàn bộ + nhả lock; tuỳ chọn “Hoàn tác thay đổi chưa commit” (chạy `git stash push -u -m "aiteams-ticket-<n>"` — **không** dùng `git checkout .`). |
| Đính kèm | Quét mime bằng magic bytes, chặn file thực thi, dọn file chờ gửi > 24h, đặt quota dung lượng/ticket (VD 200MB), xoá file khi xoá ticket; ảnh logo ≤ 300KB được resize 256px. |
| Giới hạn | `MAX_ACP_PROCESSES`, `MAX_CONCURRENT_TICKETS`, timeout mỗi lượt, giới hạn kích thước diff/terminal lưu DB (cắt + lưu file đầy đủ ra `data/blobs/`). |
| Bí mật | **API key của agent `openai-api` mã hoá Fernet (`APP_SECRET_KEY`), không trả ra API/log/audit/event, scrub `Authorization`/`sk-…` ở mọi lỗi**; hỗ trợ xoay khoá `APP_SECRET_KEY` (script re-encrypt); Không log biến môi trường; **log agent hiển thị trong chat cũng phải qua bộ scrub token** trước khi lưu/phát; scrub chuỗi giống token (`sk-`, `ghp_`, `xox`) trong `ticket_messages` trước khi lưu & phát. |
| Audit | Bảng `audit_logs` (user, action, target, payload, ip, at) cho: tạo/sửa agent (**kèm `restart` và danh sách ticket bị ảnh hưởng**), đổi permission, confirm/reject, git release, mở terminal. Trang `/settings/audit`. |
| Quan sát | Log JSON (structlog), metric đơn giản `/api/metrics` (số ticket theo trạng thái, thời gian trung bình mỗi node, số lần guard deny). |
| Sao lưu | Script backup SQLite + checkpoints hằng ngày. |
| Cập nhật adapter | Trang Settings hiển thị version `claude-agent-acp`, `codex-acp`, `claude`, `codex`; nút “Kiểm tra cập nhật” (chạy `npm view <pkg> version`). |

## 6. Đóng gói chạy trên Windows
- `scripts/install.ps1`: kiểm tra Python 3.11+, Node 20+, git; cài adapter npm global; tạo venv; `alembic upgrade head`; `npm ci && npm run build`.
- `scripts/start.ps1`: chạy backend (`uvicorn app.main:app --host 127.0.0.1 --port 8000`) + frontend (`next start -p 3000`); tuỳ chọn đăng ký Windows Service bằng NSSM.
- Mặc định chỉ bind `127.0.0.1`; muốn truy cập từ điện thoại/máy khác (kiểu 9remote) → hướng dẫn đặt sau reverse proxy có HTTPS + bắt buộc đăng nhập, **không** mở thẳng cổng.

## 7. Kiểm thử tổng
- Bộ E2E Playwright chạy với fake ACP trong CI (Linux) + checklist chạy tay với ACP thật trên Windows:
  1. Happy path (IMPLEMENTATION_PLAN §7).
  2. BA hỏi lại 2 vòng.
  3. Tester fail 2 lần rồi pass.
  4. User reject 1 lần.
  5. Model chính lỗi capacity (giả lập) → fallback thành công.
  6. Push bị reject (remote có commit mới) → ticket FAILED, commit local còn, hướng dẫn rõ.
  7. Restart backend khi đang WAITING_USER_CONFIRM → confirm vẫn chạy.
  8. Hai ticket thuộc 2 workflow khác nhau của cùng project → ticket 2 xếp hàng với thông báo rõ ràng, tự chạy khi ticket 1 xong.
  9. Remote terminal: gõ `git status` thấy output; user không phải MAINTAINER bị từ chối.
  10. Sửa cấu hình `@developer` khi ticket đang chạy → agent khởi động lại, lượt đang chạy chạy lại từ đầu node, chat hiện dòng log `↻ …`, audit ghi lại.
  11. Thông báo: ticket chờ xác nhận → badge sidebar = 1 → xác nhận trong chat → thông báo sang “Đã xử lý”; restart backend khi đang chờ → thông báo vẫn còn, không bị nhân đôi.
  12. Đính kèm: gửi ảnh + file log cho `@developer` → prompt lượt sau có đường dẫn; `@leader` không commit thư mục đính kèm.
- Kiểm thử bảo mật guard: bộ 50+ chuỗi lệnh né chặn (`g''it commit`, `git${IFS}push`, `powershell -c "git push"`, `cmd /c git push`, alias…) → tất cả bị chặn với Developer/Tester. Lệnh khó phân tích (có biến shell, eval, base64) → **mặc định deny** với profile có `blocked_commands` chứa git.

## 8. Definition of Done
- [x] Terminal từ xa hoạt động trên Windows, resize đúng, reconnect giữ phiên.
- [x] Fallback model hoạt động theo chính sách, hiển thị rõ trong chat (provider giả lập).
- [x] Bộ test né guard pass 100% (63 chuỗi × 2 profile).
- [ ] Cài đặt mới trên máy Windows sạch bằng `install.ps1` + `start.ps1` chạy được happy path.

Triển khai và bằng chứng kiểm thử: [PHASE_7_IMPLEMENTATION_NOTES.md](PHASE_7_IMPLEMENTATION_NOTES.md).
Nghiệm thu Windows sạch/native provider còn cần môi trường riêng; không bỏ policy gate Phase 3.
