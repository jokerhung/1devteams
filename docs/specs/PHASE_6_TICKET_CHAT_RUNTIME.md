# PHASE 6 — Ticket Chat Runtime (phòng chat Multi-Agent kiểu Buzz)

## 1. Mục tiêu
Màn hình `/projects/[id]/workflows/[wid]/tickets/[ticketId]` — bước cuối của thứ tự Project → Workflow → Ticket → **Chat**. Cửa sổ này **mở tự động ngay khi tạo ticket** (Phase 4 §4.6) và workflow đã bắt đầu chạy. Mỗi ticket là một **channel** (`# bug-xuat-excel`) nằm dưới workflow của nó trong sidebar. Người dùng báo lỗi, quan sát agent làm việc theo thời gian thực, trả lời BA, xác nhận/từ chối bản sửa ngay trong dòng chat. Giao diện bám **view-chat** trong `docs/aiTeams_gui.html` (dòng tin nhắn phẳng, không bong bóng màu mè).

## 2. Cấu trúc file
```text
src/app/(workspace)/projects/[id]/workflows/[wid]/tickets/[ticketId]/page.tsx
src/components/ticket-chat/
├── TicketChannel.tsx          # layout: header + stream + composer + footer; drawer phải (tùy chọn)
├── ChannelHeader.tsx          # "# bug-xuat-excel • D:\VETC\FE\HNBG_DEV (hotfix/reconciliation)" + số thành viên + nút xem workflow
├── MessageStream.tsx          # danh sách message đã gom nhóm, auto-scroll, "tin mới ↓"
├── groupEvents.ts             # gom AgentEvent → MessageGroup (theo agent_turn_start..end)
├── UserMessage.tsx
├── AgentTurn.tsx              # 1 lượt làm việc của agent (header + các block + nội dung)
├── blocks/
│   ├── ThinkingBlock.tsx      # <details> "Đang suy nghĩ…" (shimmer khi đang stream)
│   ├── ToolCallChips.tsx      # 🔍 Đã đọc src/..., ✏️ Sửa ..., ▶ Chạy npm test (trạng thái pending/completed/failed)
│   ├── FileDiffBlock.tsx      # <details> "📄 Xem thay đổi mã nguồn: ExportButton.tsx (+8 -2)"
│   ├── TerminalBlock.tsx      # khối đen: $ lệnh / output / exit code
│   ├── PermissionLog.tsx      # dòng nhỏ đỏ "Guard: Đã chặn git commit của @developer"
│   ├── PlanBlock.tsx
│   └── MarkdownContent.tsx    # react-markdown + remark-gfm + highlight code; mention → AgentPill
├── AgentLog.tsx               # log ACP gắn vào từng AgentTurn: dòng cuối + mũi tên mở rộng (mục 5.3b)
├── AgentLogDialog.tsx         # “Xem toàn bộ log của ticket”: lọc theo agent, tự cuộn, Copy
├── MentionPicker.tsx          # nút @ + popup chọn agent, nhớ lựa chọn mặc định (mục 5.7)
├── AttachmentTray.tsx         # thẻ file chờ gửi + kéo thả/dán (mục 5.7b)
├── MessageAttachments.tsx     # hiển thị file/ảnh trong tin nhắn đã gửi
├── InlineConfirmBox.tsx       # hộp xác nhận trong tin nhắn tester (mockup #confirm-box)
├── RejectFeedbackDialog.tsx
├── ClarifyPrompt.tsx          # dải nhắc phía trên composer khi BA đang chờ
├── Composer.tsx               # ô nhập + nút mention nhanh + nút gửi tròn
├── AgentStatusFooter.tsx      # "🐝 leader: Đang chờ người dùng xác nhận…" | "claude-agent-acp • codex-acp"
├── SystemDivider.tsx          # "Tiến trình Đội ngũ Agent", "Luồng quay lại @developer", ...
└── RightDrawer.tsx            # Tabs: Tiến độ (WorkflowReadonlyGraph/Pipeline) | Terminal (Phase 7)   — log ACP đã chuyển vào từng AgentTurn
src/lib/ws.ts                  # TicketSocket: connect, resume after_seq, reconnect backoff, ping/pong
src/stores/ticket-store.ts     # zustand: events by seq, groups, status, waiting, nodeStatuses, draftFiles
src/stores/chat-prefs.ts       # defaultMentionAgentId (đồng bộ user_preferences + cache localStorage)
```
Cài thêm: `npm i react-diff-viewer-continued shiki` (hoặc `react-syntax-highlighter`), `diff` (tính +/- nếu backend chỉ gửi old/new).

## 3. Luồng dữ liệu
0. Vào từ `CreateTicketDialog`: response tạo ticket đã có `ticket` → điền sẵn store (header hiện ngay, không nhấp nháy), hiển thị tin nhắn đầu tiên của user = mô tả ticket + divider “Tiến trình Đội ngũ Agent”; WS mở ngay để bắt event `agent_turn_start` của node đầu (thường là `@ba`). Kiểm tra `wid` trên URL khớp `ticket.workflow_id`, sai → redirect đúng URL.
1. Vào trang: `GET /tickets/{id}` + `GET /tickets/{id}/state` + `GET /tickets/{id}/messages?limit=500` → nạp store.
2. Mở WS `/ws/tickets/{id}?token=..&after_seq=<max seq>` → nhận `snapshot` + `event`.
3. Store gộp event theo `seq` (bỏ trùng), cập nhật `status`, `waiting`, `nodeStatuses`, `currentAgent`.
4. Action (start/reply/confirm/cancel/messages) gọi REST (Phase 3 §11.1); UI cập nhật lạc quan cho tin nhắn user (pending → xác nhận khi event về có `client_msg_id` trùng).
5. Mất kết nối → banner vàng “Đang kết nối lại…”, backoff 1s→2s→5s→10s, resume bằng `after_seq`.

## 4. Gom nhóm hiển thị (`groupEvents.ts`)
- `USER` message → `UserMessage`.
- `agent_turn_start` mở một `AgentTurn` (key `run_id`); các event cùng `run_id` gắn vào turn: `thought_chunk` → nối vào thinking; `message_chunk` → nối vào content; `tool_call`/`tool_call_update` → cập nhật chip theo `tool_call_id`; `file_edit` → thêm FileDiffBlock (gộp nhiều lần sửa cùng file thành 1 diff cuối, giữ diff tổng); `terminal_output` → TerminalBlock; `permission` (allowed=false) → PermissionLog.
- **Log dòng (`logLines`) của turn**: mọi event cùng `run_id` thuộc loại `tool_call`, `tool_call_update`, `permission`, `thought_chunk` (tóm 1 dòng), `plan`, `error` và dòng hệ thống của engine (`→ session/new`, `→ session/prompt`, `✔ stopReason=end_turn`) được chuẩn hoá thành `LogLine {at, kind: info|tool|perm|deny|think|ok|error, text}` (hàm `toLogLine(event)`, ví dụ `tool: Edit ExportButton.tsx (+8 −2)`, `permission: Bash git commit → DENY (blocked_commands)`). Mảng này gắn vào `AgentTurn.logLines`.
- `agent_turn_end` đóng turn (tắt shimmer, hiện thời gian chạy).
- `gate_waiting` kind `human_confirm` → gắn `InlineConfirmBox` vào **cuối turn agent gần nhất** (tester); kind `human_input` → bật `ClarifyPrompt`.
- `ticket_status` → cập nhật header/footer, chèn `SystemDivider` khi đổi hướng luồng (VD `rejected` → “🔄 Luồng đã quay lại @developer”).
- Hiệu năng: virtualize khi > 300 group (`@tanstack/react-virtual`); render markdown chỉ khi turn kết thúc hoặc throttle 200ms khi đang stream.

## 5. Chi tiết UI (theo mockup)

### 5.1. ChannelHeader
Breadcrumb nhỏ phía trên: `HNBG_DEV / ⑂ Fix Bug (v3) / #BUG-104` (click workflow → trang workflow). Dòng chính: `# bug-xuat-excel` (đậm) • `D:\VETC\FE\HNBG_DEV (hotfix/reconciliation)` (mono, xám) — phải: icon users + số (user + effective agents), `StatusBadge`, nút ⚙ mở RightDrawer, menu ⋯ (Huỷ ticket, Thử lại, Sao chép link).

### 5.2. UserMessage
Avatar initials tròn `stone-800`, tên đậm `text-xs`, giờ `text-[11px] stone-400`, nội dung 13.5px; mention `@ba` render thành `AgentPill`.

### 5.3. AgentTurn
- Avatar emoji theo agent (🐝 🛠️ 🧪 🚀 🤖), tên `handle` không `@` đậm, chip model mono (`claude-3-7-sonnet` → hiển thị đúng `metadata.model_effective`), giờ.
- Thứ tự block: Thinking (thu gọn) → Tool chips → Nội dung markdown → File diffs → Terminal blocks → Permission logs → Reactions (tùy chọn) → InlineConfirmBox (nếu có).
- Khi đang chạy: dòng “đang gõ…” 3 chấm + shimmer.

### 5.3b. Log agent gắn vào từng dòng chat (AgentLog)
Mỗi `AgentTurn` có **một dòng log ngay dưới tiêu đề (tên agent · model · giờ)**, phía trên nội dung:
- **Thu gọn (mặc định): chỉ hiện DÒNG LOG CUỐI CÙNG** của lượt đó (VD `✔ push thành công`, `✔ stopReason=end_turn`), tô màu theo `kind` (ok xanh, deny đỏ, perm vàng nâu, tool xám đậm, think tím, info xám nhạt), `truncate` 1 dòng, kèm **mũi tên ⌄**.
- **Bấm mũi tên → mở rộng**: danh sách *toàn bộ* log lines của lượt (mỗi dòng: nội dung + giờ `HH:mm:ss` bên phải), khung trắng bo góc, cao tối đa ~16rem và cuộn; cuối danh sách có liên kết **“Xem toàn bộ log của ticket →”** mở `AgentLogDialog`. Trạng thái mở/đóng nhớ theo turn (giữ khi re-render).
- **Khi agent đang chạy** (`agent_turn_start` chưa có `agent_turn_end`): dưới dòng “@x đang làm việc …” hiện cùng thành phần với chấm xanh nhấp nháy; dòng cuối **đổi liên tục** theo event mới; người dùng mở rộng giữa chừng thì danh sách giữ nguyên trạng thái mở và tự thêm dòng mới (auto-scroll chỉ khi đang ở cuối). Xong lượt → chấm tắt, dòng cuối cố định.
- **Agent `openai-api`**: log của lượt có dạng `→ POST <host>/chat/completions (<model>, stream)` → `đang nhận phản hồi từ API...` → `tokens: prompt N · completion M` → `✔ finish_reason=stop`; không có `tool_call`, `file_edit`, `terminal_output`, `permission` (agent text-only) nên turn chỉ có nội dung markdown, **không có FileDiffBlock/TerminalBlock**; huy hiệu model trên header turn hiển thị tên model API.
- Turn không có log line (VD turn của user, SYSTEM) → không hiện `AgentLog`.
- `AgentLogDialog`: cửa sổ lớn (max-w-4xl, nền tối, mono 11px, cao 60vh): bộ lọc **Tất cả agent / @agent**, đếm dòng, tự cuộn xuống cuối (dừng nếu người dùng cuộn lên), nút **Copy** (`HH:mm:ss @agent text`). Dữ liệu từ store; phân trang lịch sử bằng `GET /tickets/{id}/logs`.
- Thay thế khung “Log ACP” trong RightDrawer ở bản đầu; **không có khung log cố định phía trên composer**.

### 5.4. FileDiffBlock
`<details>` header “📄 Xem thay đổi mã nguồn: `ExportButton.tsx` (+8 −2)” · “Bấm để mở”; mở ra: diff unified (dòng `-` nền rose-50 chữ rose-700, `+` nền emerald-50 chữ emerald-700, mono 12px); nút “Xem toàn màn hình” → Dialog dùng `react-diff-viewer-continued` split view.

### 5.5. InlineConfirmBox (Human-in-the-loop)
Hộp `bg-[#F7F6EE] border-[#DFDDD0] rounded-xl p-3 max-w-xl`:
- Trái: “Bạn xác nhận lỗi đã được sửa xong?” (+ danh sách file sẽ commit, thu gọn).
- Phải: nút viền **Chưa đạt, sửa lại** → `RejectFeedbackDialog` (textarea bắt buộc, gợi ý “Mô tả điểm chưa đạt để @developer sửa lại”) → `POST /confirm {approved:false, feedback}`; nút đen **✓ Xác nhận (Báo @leader Push Git)** → `POST /confirm {approved:true}`.
- Sau khi gửi: hộp chuyển trạng thái read-only “Đã xác nhận bởi Nguyen Manh Hung lúc 9:22” / “Đã yêu cầu sửa lại”.
- Chỉ user có quyền confirm mới thấy nút; người khác thấy “Đang chờ MAINTAINER xác nhận”.

### 5.6. ClarifyPrompt (BA hỏi lại)
Khi `waiting.kind === "human_input"`: dải nhắc phía trên Composer, viền sky: “🐝 **@ba** đang chờ bạn cung cấp thêm chi tiết để hoàn tất kịch bản tái tạo lỗi…”, focus Composer; gửi → `POST /reply`.

### 5.7. Composer
Khung viền bo `rounded-xl`: (a) hàng thẻ file chờ gửi (ẩn khi rỗng), (b) ô nhập 1 dòng, (c) thanh dưới: **[nút @] [nút 📎]** bên trái, **nút gửi tròn** bên phải. Nút đính kèm nằm **ngay bên phải nút @**.
- Placeholder: có agent mặc định → `Nhắn tin vào #bug-xuat-excel — mặc định gửi tới @developer...`; chưa có → `Nhắn tin vào #bug-xuat-excel (bấm nút @ để chọn agent)...`.
- **Nút @ (`MentionPicker`)**: hiển thị `Logo @handle ⌃` của agent mặc định, hoặc `@ Chọn agent` nếu chưa chọn. Bấm → **popup nổi phía trên** (w-72): tiêu đề “Gửi tới agent (lưu làm mặc định)”, mỗi dòng = avatar `Logo` + `@handle` (mono, đậm) + tên agent, dấu ✓ cho agent mặc định; cuối popup nút “Bỏ mặc định” khi đang có mặc định. Bấm ra ngoài / Esc để đóng.
  - **Chọn một agent = đặt làm mặc định** cho mọi chat tiếp theo: lưu `user_preferences.default_mention_agent_id` (`PUT /me/preferences`) + cache `localStorage('aiteams_default_mention')`; áp dụng cho mọi ticket/project (nếu agent không thuộc effective agents của project đang mở thì coi như chưa chọn). Toast “Mặc định gửi tới @x cho các chat tiếp theo”.
  - **Khi gửi**: nếu tin nhắn **chưa chứa `@agent` nào** → client tự thêm `@<mặc định> ` vào đầu; nếu người dùng đã gõ `@agent` khác thì giữ nguyên. Backend không biết đến “mặc định” — chỉ nhận text đã có mention (Phase 3 §11.3).
  - Gõ `@` trong ô nhập vẫn mở autocomplete (popover) như trước.
- Enter gửi, Shift+Enter xuống dòng. Gửi → `POST /tickets/{id}/messages {text, attachment_ids}`; có thể **gửi chỉ file không cần chữ**.
- Ticket `OPEN`: nút **▶ Bắt đầu xử lý** nổi bật thay vì composer trống. Ticket `COMPLETED`/`CANCELLED`: composer và đính kèm bị vô hiệu + thông báo.

### 5.7b. Đính kèm file (Attachments)
- **3 cách thêm**: bấm nút 📎 (chọn nhiều file), **kéo thả** vào khung composer (viền sáng khi kéo qua), **dán ảnh** (Ctrl+V) vào ô nhập.
- **Giới hạn**: tối đa **5 file/tin nhắn**, mỗi file ≤ **10 MB** (cấu hình `ATTACH_MAX_FILES`, `ATTACH_MAX_MB`); vượt → toast “Tối đa 5 file mỗi tin nhắn” / “<tên> vượt quá 10MB”.
- **Thẻ chờ gửi** (`AttachmentTray`): ảnh → thumbnail 32px; file khác → icon theo loại (ảnh, nén, text/log/json/csv, code, mặc định) + tên (truncate) + dung lượng; nút ✕ gỡ. Mỗi file upload ngay khi thêm (`POST /tickets/{id}/attachments`, hiện tiến trình), giữ `attachment_id`; danh sách chờ lưu **riêng theo ticket** (đổi ticket không mất, gửi xong thì xoá).
- **Trong tin nhắn đã gửi** (`MessageAttachments`): ảnh hiện trực tiếp (max-h 160px, click phóng to), file khác là thẻ (icon + tên + dung lượng, click tải về).
- **Với agent**: sau khi gửi, backend ghi file vào `<workspace>/.aiteams/attachments/<ticket>/<tên>` (hoặc thư mục tạm ngoài repo — cấu hình), đưa **đường dẫn + mô tả** vào prompt lượt kế tiếp của agent được mention; ảnh có thể gửi dưới dạng content block hình ảnh nếu runtime hỗ trợ. Thư mục này nằm trong `.git/info/exclude` để `@leader` không commit nhầm (Phase 3 §7).

### 5.7c. Liên kết với Thông báo
Khi ticket chuyển `WAITING_USER_CONFIRM` / `WAITING_USER_INPUT`, backend tạo thông báo tương ứng (Phase 4 §4.7). Click thông báo → mở chat, **cuộn tới và nhấp nháy** `InlineConfirmBox` / `ClarifyPrompt` đang chờ. Khi người dùng xử lý ngay trong chat, thông báo tự chuyển sang “Đã xử lý”.

### 5.8. AgentStatusFooter
Thanh dưới cùng `text-[11px]`: trái `🐝 <handle>: <trạng thái>` (VD “developer: Đang sửa ExportButton.tsx…”, lấy từ tool_call mới nhất; “leader: Đang chờ người dùng xác nhận để commit & push Git”; “Hoàn tất: Commit 8c3d91a đã được đẩy lên Git.”), phải `claude-agent-acp • codex-acp` + đèn trạng thái WS.

### 5.9. RightDrawer (đóng mặc định để giữ giao diện tối giản)
- Tab **Tiến độ**: `WorkflowReadonlyGraph` (Phase 5) của **đúng version workflow mà ticket dùng** (`GET /workflows/{wid}/versions/{ticket.workflow_version}`) tô màu theo `nodeStatuses`; dưới là timeline các bước với thời lượng.
- Tab **Terminal**: placeholder, làm ở Phase 7.

### 5.10. Sidebar cập nhật realtime
Badge trạng thái của channel trong sidebar (VD “Chờ duyệt” → “Đã xong”) cập nhật qua WS `/ws/projects/{id}` (kênh nhẹ chỉ phát `ticket_created`, `ticket_status`); **badge “Thông báo”** cập nhật qua WS `/ws/users/me` (`notification_created`, `notification_resolved`). Cả hai kênh là mở rộng nhỏ của Phase 3 §11.2.

## 6. Kết thúc ticket
Khi `release` về: AgentTurn của `@leader` có TerminalBlock các lệnh git + câu tổng kết; header đổi `StatusBadge` “Đã xong”; card tóm tắt cuối channel: commit hash (copy được, link tới remote nếu là GitHub/GitLab), branch, danh sách file, +/−.

## 7. Test
- Unit `groupEvents.test.ts`: chuỗi event mẫu (fixture JSON xuất từ test engine Phase 3) → đúng số group, diff gộp đúng, confirm box gắn vào turn tester.
- Unit `ticket-store.test.ts`: event trùng seq bị bỏ; resume after_seq.
- Playwright `ticket.spec.ts` với **backend chạy fake ACP** (biến môi trường `ACP_FAKE_SCENARIO=bugfix_happy_path`):
  1. Mở workflow *Fix Bug* → **+ Tạo ticket** “Bấm nút xuất Excel trên màn hình đối soát không tải được file” → **Tạo & mở chat** → URL chuyển sang `/workflows/[wid]/tickets/[ticketId]`, channel mới xuất hiện dưới workflow *Fix Bug* trong sidebar, `@ba` bắt đầu ngay (không cần bấm Bắt đầu).
  2. Thấy turn @ba hỏi lại → trả lời trong composer → thấy STR.
  3. Thấy @developer + FileDiffBlock + PermissionLog “chặn git commit”.
  4. Thấy @tester PASS + InlineConfirmBox → bấm Xác nhận.
  5. Thấy @leader + commit hash, status “Đã xong”.
  6. **Log gắn vào turn**: mỗi turn của @ba/@developer/@tester/@leader có `AgentLog` chỉ hiện dòng cuối; bấm mũi tên → thấy đủ các dòng (kể cả dòng `permission … DENY` của @developer); khi @leader đang chạy dòng cuối đổi liên tục và danh sách đang mở không bị đóng.
  7. **Composer**: bấm @ → chọn `@developer` → gửi “hãy làm nhanh” → tin nhắn hiển thị mention `@developer`; mở ticket khác → nút @ vẫn là `@developer`; đính kèm 1 ảnh + 1 file log (kéo thả), gỡ 1 file, gửi → ảnh hiện trong tin nhắn; thêm file thứ 6 → bị từ chối.
  8. **Thông báo**: ở bước tester PASS có thông báo “Cần xác nhận”, badge sidebar = 1; bấm Xác nhận → thông báo sang tab “Đã xử lý”, badge ẩn.
  9. Kịch bản phụ: bấm “Chưa đạt” + feedback → thấy divider “quay lại @developer”.
- Test reconnect: tắt WS giữa chừng → bật lại → không mất/không trùng tin nhắn.

## 8. Definition of Done
- [ ] Chạy E2E thật (Claude Code/Codex thật) trên bản copy `HNBG_DEV` đạt đủ 6 bước ở IMPLEMENTATION_PLAN §7.
- [ ] Độ trễ hiển thị chunk < 300ms từ lúc backend nhận.
- [ ] Giao diện khớp mockup `view-chat` (so screenshot): log gắn từng turn (dòng cuối + mũi tên), nút @ popup, nút 📎 bên phải nút @, thẻ file chờ gửi.
- [ ] Agent mặc định của nút @ được nhớ qua ticket, qua project và sau khi tải lại trang.
- [ ] Đính kèm: 3 cách thêm, giới hạn 5 file/10MB, agent nhận được đường dẫn file trong prompt.
- [ ] Mở 2 tab trình duyệt cùng ticket → cả 2 đồng bộ realtime; confirm ở tab 1 → tab 2 ẩn nút.
