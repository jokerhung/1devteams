# Phase 3 — Workflow Engine

## Trạng thái

Đã triển khai engine, API và realtime. **Chưa đạt toàn bộ Definition of Done**:
acceptance chạy native Claude/Codex trên bản copy HNBG_DEV đang bị chặn bởi policy gate
đã có từ Phase 1. Không bật `diagnostic` hay tự nhận `client_tools_only` cho adapter native.

## Thành phần đã triển khai

- `engine/state.py`: state serialize được, outputs/user inputs có reducer nối lịch sử;
  iteration, route, cursor từng session, gate counter, approval và trạng thái node.
- `engine/compiler.py`: dùng validator Phase 2, biên dịch LangGraph động, conditional edges,
  vòng lặp, START/END; cache runner theo workflow/version, recursion limit 100.
- `engine/markers.py`, `conditions.py`, `prompts.py`: marker mới/cũ, bổ sung prompt một lần
  khi thiếu marker, fallback an toàn, ReleasePlan chặt kiểu; mini-parser condition không eval;
  prompt đầu đủ ticket, prompt sau chỉ thêm output/feedback mới, giới hạn context.
- `engine/context.py`, `nodes.py`: dependencies trong RunnableConfig; stream ACP/API,
  gộp chunk 150 ms, lưu DB trước khi fan-out; run_id, session logs, turn start/end;
  retry runtime một lần và chạy lại khi cấu hình thay đổi, kể cả trong handshake.
- API agent chỉ nhận văn bản: diff mỗi file tối đa 12.000 ký tự, tổng mặc định 40.000;
  tối đa 5 context files cho BA/review, qua path guard, chặn `.env` và traversal;
  không gửi tools, không ghi nhận sửa file, không dùng làm developer/tester/git_release.
- `interrupt()` cho INPUT/CONFIRM và giới hạn iteration; gate key ổn định khi node replay;
  notification tạo idempotent, resolve ANSWERED/APPROVED/REJECTED/CANCELLED/FAILED.
- `runner.py`: start/reply/confirm/cancel/retry, background registry, snapshot đã publish;
  khóa theo workspace canonical dùng chung giữa workflow/project cùng workspace, xếp hàng FIFO.
  Giữ khóa khi WAITING_CONFIRM hoặc đã chạy agent có quyền ghi; chỉ nhả ở INPUT trước agent ghi.
  Ticket xếp hàng giữ OPEN và có system message giải thích ticket/workflow đang giữ khóa.
- Recovery: RUNNING chuyển FAILED với lý do server restart; retry tiếp tục checkpoint;
  WAITING giữ interrupt và khôi phục khóa. Shutdown cancel task, đóng session, nhả khóa.
- `services/git_service.py`: subprocess exec, whitelist lệnh, timeout 120 giây và dừng process tree;
  status/diff/branch, lọc file nhạy cảm, loại `.aiteams/attachments`, thêm git exclude;
  commit Conventional Commits và push remote/branch rõ ràng, từ chối detached HEAD.
  Không chạy hooks, fsmonitor, external diff/textconv hoặc ký commit/push tự động.
  `commit --only` không gom file khác đã staged của người dùng. Push lỗi giữ commit local,
  không tự pull/rebase; lưu terminal output đã lọc URL credentials.
- `core/events.py`: sequence DB tăng nguyên tử, counter khởi tạo/khôi phục từ max seq;
  subscriber queue tối đa 1000, ngắt consumer chậm bằng close 1013 để reconnect/replay.
- Ticket actions REST; chat tự do parse mention; tệp gắn message, copy vào thư mục ticket,
  có path guard và git exclude. ACP gửi image blocks khi adapter quảng bá hỗ trợ ảnh;
  API agent nhận mô tả/đường dẫn và thông báo rõ không có công cụ đọc tệp.
- `ws/ticket_ws.py`: ticket snapshot, replay seq, live events, ping 25 giây, actions chung runner;
  subscribe trước replay, dedupe và đọc gap DB để không mất event khi commit/publish lệch thứ tự.
  Project channel phát ticket_created/ticket_status với workflow_id; user channel giữ notification/restart.
  Token qua first frame hoặc Authorization được ưu tiên; hỗ trợ query token theo spec để tương thích.
  Ticket/project WS kiểm tra lại token và quyền trước khi tiếp tục gửi.

## Chạy local với SQLite

Giữ các khóa và mật khẩu hiện có trong `backend/.env`:

```dotenv
DATABASE_URL=sqlite+aiosqlite:///./aiteams.db
CHECKPOINT_DB=./checkpoints.db
MAX_NODE_ITERATIONS=5
API_CONTEXT_DIFF_CHARS=40000
```

`CHECKPOINT_DB` tương đối được neo vào `backend/`. Backup database, checkpoint DB và `data/`;
giữ `APP_SECRET_KEY` ổn định. Không xóa checkpoint DB khi còn ticket WAITING.

```powershell
.\scripts\dev.ps1 -Setup
```

Runner hiện chỉ hỗ trợ **một backend worker**. EventBus, workspace lock và task registry nằm
trong một tiến trình; chưa có distributed lock hoặc Redis Pub/Sub.

Linux production có thể đặt `CHECKPOINT_POSTGRES_URL=postgresql://.../checkpoint_database`
để dùng AsyncPostgresSaver (schema tự setup). URL này tách biệt với DATABASE_URL của SQLAlchemy.
Windows giữ SQLite checkpointer vì psycopg async không hỗ trợ ProactorEventLoop mà ACP subprocess cần.
Không chuyển Windows sang SelectorEventLoop để lách lỗi này.

## API

Các đường dẫn REST có prefix `/api`:

| Action | Method/path | Body |
|---|---|---|
| Start | POST `/tickets/{id}/start` | — |
| Reply | POST `/tickets/{id}/reply` | `{text}` |
| Confirm | POST `/tickets/{id}/confirm` | `{approved, feedback?}` |
| Cancel/retry | POST `/tickets/{id}/cancel`, `/retry` | — |
| Chat | POST `/tickets/{id}/messages` | `{text?, attachment_ids?}` |
| State | GET `/tickets/{id}/state` | — |

Start/reply/cancel/retry yêu cầu quyền report trên project; confirm yêu cầu MAINTAINER
(owner/system admin theo quyền Phase 2). Không bật tùy chọn reporter tự approve ở phiên bản này.
`auto_start=true` được nối runner ngay sau commit tạo ticket; response có `auto_start_pending=false`.
Task chạy nền nên trạng thái trong response tạo có thể còn OPEN trong lúc chờ scheduler/workspace.

Browser WS `/ws/tickets/{id}?after_seq=0`: gửi frame đầu `{"token":"..."}`, nhận snapshot,
sau đó `{type:"event", data:...}`. Action: `{type:"action", action:"confirm", approved:true}`.
Phản hồi action riêng `{type:"action_result", accepted:...}`. JWT query được hỗ trợ theo spec;
nên dùng first frame để tránh token xuất hiện trong URL/access log.

## Kiểm chứng

Kết quả ngày 2026-10-23:

- Rà soát bổ sung: lỗi runtime/restart được lưu vào `state.error`, retry giữ đúng node cần chạy;
  hủy ticket và đọc state/checkpoint không phụ thuộc việc compile lại snapshot hay agent còn active.
  Log Git chia thành các event tối đa 100.000 ký tự, giữ toàn bộ output sau khi che thông tin
  xác thực trong URL và chuyển NUL thành newline để lưu được trên PostgreSQL.
- Linux PostgreSQL 16 + AsyncPostgresSaver: **4 passed** cho regression cancel khi agent inactive,
  failure/retry, input gate/notification và reopen checkpoint bằng kết nối mới sau các sửa đổi này.

- Windows Python 3.12 + SQLite, lượt cuối sau rà soát: **159 passed, 1 skipped, 4 deselected**. Skip là test symlink
  do host không có quyền tạo; 4 test real ACP/API opt-in không nằm trong suite thường.
- Linux Python 3.12 + SQLite, source mount read-only: **157 passed, 4 deselected** ở lượt full suite;
  hai test bổ sung restart trong handshake và mở checkpoint bằng kết nối mới được xác minh trên
  Windows và trong suite PostgreSQL dưới đây.
- Linux PostgreSQL 16 + AsyncPostgresSaver, hai database tạm riêng cho data/checkpoint:
  **71 passed, 1 deselected** (`tests/api tests/engine`). Đã sửa lỗi NUL trong log porcelain Git
  mà SQLite chấp nhận nhưng PostgreSQL từ chối.
- Ruff lint/format và mypy: pass. Hai test release/reopen được chạy lại sau chỉnh run_id: pass.
- Docker test containers và cache volume của Phase 3 đã được dọn; không dừng dịch vụ dev đang có.

Test thường không gọi CLI/provider thật;
test ACP protocol dùng một executable JSON-RPC peer, đầy đủ fs/permission/stream và image blocks.
Các integration test Git dùng repo tạm và remote bare tạm, không push lên remote dự án thật.

```powershell
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run pytest tests/engine
# Opt-in acceptance native trên clone tạm:
uv run pytest tests/engine/test_real_workflow.py -m real_acp
```

Acceptance native đã chạy ngày 2026-10-23: clone `D:\VETC\FE\HNBG_DEV` vào Temp,
đổi origin của clone thành remote bare tạm, tạo project/workflow/ticket. Runner dừng FAILED
với thông báo adapter native chưa xác minh công cụ qua guard. Không chạy prompt native,
không sửa repository nguồn, không push remote nguồn. Chỉ khi có client-only routing hoặc
sandbox đã kiểm chứng mới có thể đạt kiểm chứng native của Phase 3.

Các file mới tập trung ở `engine/`, `services/git_service.py`, `ws/` và `tests/engine/`.
WebSocket auth/replay/transport nằm chung `ws/ticket_ws.py`; chưa tách `ws/manager.py` vì
EventBus đã cung cấp fan-out. Không triển khai giao diện Phase 4–6.
