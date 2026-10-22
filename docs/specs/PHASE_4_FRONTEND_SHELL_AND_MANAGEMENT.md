# PHASE 4 — Frontend Shell (Buzz-minimal) & Quản lý Agent / Team / Project / Member

## 1. Mục tiêu
- Dựng khung giao diện Next.js **bám sát mockup `docs/aiTeams_gui.html`** (bản đã chốt 22/10/2026): sidebar màu kem bên trái + panel nội dung trắng bo góc bên phải.
- Hoàn thiện các màn hình quản trị: **Agents & Teams (một trang)**, Projects (tổng quan + settings + members), **Thông báo**. Ticket chat và Workflow builder làm ở Phase 5–6 (phase này chỉ tạo route/placeholder).

> **Đồng bộ với mockup (đã bỏ / đổi so với bản đầu):** bỏ ô “Tìm kiếm mọi thứ ⌘K”; bỏ tab “Tổng quan & Workflows”; bỏ mục “Đội ngũ Agent trong kênh/project” ở sidebar; “Hộp thư” đổi thành **Thông báo**; hai tab AI Agents + AI Teams gộp thành **một tab “Agents & Teams”**; tạo project chỉ tạo **project trống**.

## 2. Design system (trích từ mockup)

### 2.1. Tokens → `tailwind.config.ts` / CSS variables trong `globals.css`
| Token | Giá trị | Dùng cho |
|-------|---------|---------|
| `--app-bg` (sidebar) | `#EBE9D8` | nền body + sidebar |
| `--sidebar-hover` | `#DFDDD0` (60% opacity khi hover) | item hover, ô search |
| `--sidebar-active` | `#D6D4C4` | channel đang chọn |
| `--pill-bg` / `--pill-border` | `#EFECE1` / `#DFDDD0` | chip mention `@ba` |
| `--confirm-bg` | `#F7F6EE` | hộp xác nhận inline |
| `--panel-bg` | `#FFFFFF`, border `stone-300/80`, `rounded-2xl`, `shadow-sm` | panel chính |
| `--fg` | `#1C1C1A` | chữ chính |
| Font | Inter (UI), JetBrains Mono (code, handle, model) | `next/font/google` |
| Cỡ chữ | sidebar 13px; message 13.5px `leading-relaxed`; meta 11px | |
| Scrollbar | 5px, thumb `#D5D3C2` | |

Map vào shadcn: `--background` = panel trắng, `--muted` = stone-100, `--border` = stone-200, `--primary` = stone-900 (nút chính đen như mockup), `--radius` = 0.75rem. Light mode là mặc định (mockup sáng); dark mode để sau.

### 2.2. Màu & icon theo agent
`color` của agent (`sky`, `amber`, `emerald`, `purple`, `stone`…) → hàm `agentColorClasses(color)` trả class avatar (`bg-amber-100 border-amber-300 text-amber-800`), dùng chung cho sidebar, chat, canvas. Safelist các class trong Tailwind config vì sinh động.

### 2.2b. Logo (agent & team)
- Mỗi agent/team có **logo**: chọn 1 trong 24 emoji có sẵn (`🤖 🐝 🛠️ 🧪 🚀 🛡️ 🦾 🧠 🔍 📝 🧑‍💻 👾 🦉 🦊 🐙 🐞 ⚙️ 🔒 📊 🎯 ⚡ 🌟 🧩 🏗️`) **hoặc tải ảnh lên** (png/jpg/webp, ≤ 300 KB → `POST /assets/logo`, trả `logo_url`).
- Component `LogoPicker` (dùng trong AgentForm và TeamForm): ô xem trước 48px + lưới emoji + nút “Tải ảnh lên”. Giá trị: `icon` (emoji) hoặc `logo_url` (ưu tiên nếu có).
- Component `Logo` (`<Logo entity size>`) hiển thị ảnh hoặc emoji — dùng ở thẻ agent/team, avatar chat, danh sách chọn agent, popup `@`.

### 2.3. Component nền tảng (`src/components/ui-app/`)
- `AgentPill` — chip `@handle` (icon bot nhỏ + tên, nền `--pill-bg`), click → chèn mention vào ô chat.
- `AgentAvatar` — `Logo` (emoji hoặc ảnh) trong ô tròn 32px theo màu agent.
- `UserAvatar` — initials trên nền `stone-800`.
- `StatusBadge` — map trạng thái ticket → nhãn tiếng Việt: `RUNNING` “Đang chạy”, `WAITING_USER_INPUT` “Chờ trả lời”, `WAITING_USER_CONFIRM` “Chờ duyệt”, `COMPLETED` “Đã xong”, `FAILED` “Lỗi”, `CANCELLED` “Đã huỷ”.
- `RuntimeBadge` — `Claude Code` / `Codex` (font mono, nền stone-100) / **`OpenAI Custom`** (nền sky-100, chữ sky-800; kèm host của Base URL ở chân card).
- `PermissionBadges` — Read-only / Read/Write / Run Test / Git Push.
- `LogoPicker`, `Logo` (mục 2.2b).
- `EmptyState`, `ConfirmDialog`, `PageHeader` (tiêu đề `text-base font-bold` + mô tả `text-xs text-stone-500` + action bên phải).

## 3. Layout & routing

```text
src/app/
├── layout.tsx                  # QueryClientProvider, Toaster, font
├── login/page.tsx
├── (workspace)/layout.tsx      # AppShell: Sidebar + <main class="flex-1 bg-white rounded-2xl ...">
│   ├── page.tsx                # redirect → project hoạt động gần nhất / trang chọn project
│   ├── notifications/page.tsx  # "Thông báo": việc cần tôi tương tác (Phase 4 §4.7)
│   ├── agents/page.tsx         # "Agents & Teams": 2 phần Agents + Agent teams trong cùng 1 trang
│   ├── teams/page.tsx          # redirect 308 → /agents (giữ link cũ)
│   └── projects/
│       ├── page.tsx            # danh sách TẤT CẢ project (modal “Xem tất cả” ở sidebar dẫn tới đây)
│       └── [id]/
│           ├── page.tsx        # tổng quan project (mở khi click TÊN project ở sidebar)
│           ├── settings/page.tsx
│           ├── members/page.tsx
│           └── workflows/
│               ├── page.tsx                      # danh sách workflow + nút "Tạo workflow"
│               ├── new/page.tsx                  # wizard tạo workflow (Phase 5)
│               └── [wid]/
│                   ├── page.tsx                  # tổng quan workflow: danh sách ticket + nút "Tạo ticket"
│                   ├── edit/page.tsx             # canvas kéo thả (Phase 5)
│                   └── tickets/[ticketId]/page.tsx # cửa sổ chat (Phase 6)
```

### 3.0. Thứ tự tạo trên UI: Project → Workflow → Ticket → Chat (mỗi bước độc lập)
| Bước | Màn hình | Điều kiện / điều hướng |
|------|----------|------------------------|
| 1 | **Tạo Project** — hộp thoại chỉ có **Tên, Đường dẫn thư mục local, Nhánh Git** | Xong → tạo **project trống** (chưa có AI Team, workflow, ticket), mở **trang tổng quan project** và toast “Đã tạo project trống. Thêm AI Team, workflow và ticket sau.” **Không** tự bật hộp thoại tạo workflow. |
| 1b | **Thêm AI Team / Agent** (nút “Thành viên & AI Team” ở tổng quan) | Tổng quan hiện cảnh báo đỏ “Chưa có agent nào — hãy thêm AI Team trước khi tạo workflow” khi effective agents rỗng. |
| 2 | **Tạo Workflow** (nút “Tạo workflow” / “+ Thêm workflow” ở sidebar / “Tạo workflow đầu tiên”) | Project chưa có workflow → `EmptyState` “Project chưa có workflow. Tạo workflow để bắt đầu nhận ticket.”; **không** có nút tạo ticket. Workflow `DRAFT` → nút tạo ticket disable, tooltip “Xuất bản workflow trước”. |
| 3 | **Tạo Ticket** | Chỉ trong ngữ cảnh một workflow `PUBLISHED`: nút **+** cạnh tên workflow ở sidebar, hoặc nút “Tạo ticket” ở trang workflow. |
| 4 | Cửa sổ chat | Tạo ticket thành công → `router.push(chat_url)`; workflow tự chạy (`auto_start`). |

Thanh bước “1. Project › 2. Workflow › 3. Ticket › 4. Chat” chỉ hiển thị ở đầu hộp thoại **Tạo Workflow** và **Tạo Ticket** (bước 2, 3) và ở dải tiến trình trên trang tổng quan project; hộp thoại **Tạo Project không có thanh này**.

### 3.1. `Sidebar` (w-60, padding phải 10px, text 13px) — theo mockup từ trên xuống
1. Hàng trên: 3 chấm cửa sổ + chấm trạng thái `ACP Connected` / `ACP lỗi` (poll `/api/health` 30s; tooltip chi tiết claude/codex). **Không có ô tìm kiếm.**
2. Menu (2 mục):
   - **Thông báo** (icon chuông) + badge số thông báo **chưa xử lý** (ẩn khi = 0) — `GET /notifications/unread-count`, cập nhật realtime qua WS `/ws/users/me`.
   - **Agents & Teams** (icon bot) + số đếm dạng `5 · 2` (agent · team) → `/agents`.
3. Tiêu đề **Projects** + nút `＋` (Tạo project mới).
4. **Danh sách project: 5 project gần nhất**, kiểu ChatGPT Desktop:
   - Sắp theo `projects.last_activity_at` giảm dần (cập nhật **chỉ khi** tạo project hoặc tạo ticket mới). **Click project KHÔNG làm đổi thứ tự.**
   - Project đang xem mà không nằm trong top 5 → được **ghim vào vị trí thứ 5** (thay project thứ 5) để luôn thấy.
   - Mỗi hàng: [icon thư mục + **tên project** (click → mở **trang tổng quan project** và tự mở rộng cây)] — [chấm vàng nếu có ticket đang chờ user] — [**nút chevron bên phải** để tự thu gọn/mở rộng cây].
   - **Không tự collapse** project hiện tại khi mở project khác; mỗi project có trạng thái `open` riêng (lưu `localStorage`, key `sidebar.open.<projectId>`).
   - Cuối danh sách: **“Xem tất cả (N)”** (hiện khi có > 5 project) → modal liệt kê mọi project, click → mở tổng quan project đó (và mở rộng cây).
5. Cây khi project mở rộng (`GET /projects/{id}/tree`, cập nhật qua WS `/ws/projects/{id}`; tải lazy khi mở lần đầu):
   ```text
   📁 HNBG_DEV (VETC)        •      [⌄]
     ⑂ Fix Bug  BUG                 [+ ticket]
        # bug-xuat-excel   Chờ duyệt
        # bug-format-tien-te   •
     ⑂ Fix Bug + Security  SEC       [+ ticket]
        Chưa có ticket
     ⑂ Làm tính năng  FEAT · nháp    (xám, không có + ticket)
     ＋ Thêm workflow
   ```
   - Project chưa có workflow: dòng xám “Chưa có workflow.” + link **“+ Tạo workflow đầu tiên”**.
   - Mỗi workflow là nhóm thu gọn được (nhớ trong localStorage), hiển thị ≤ 15 ticket mới nhất + “Xem tất cả”.
   - Mỗi ticket là channel `# <channel_slug>` + badge trạng thái nhỏ; item đang mở dùng `--sidebar-active`.
6. Đáy: user card (initials, tên, `workspace_path` của project hiện tại font mono), menu: đăng xuất.

State project hiện tại: URL (`/projects/[id]/...`) + `localStorage` (`lastProjectId`).

## 4. Màn hình quản trị

### 4.1. `/agents` — “Agents & Teams” (một trang, hai phần xếp dọc)
Phần **Agents** ở trên, phần **Agent teams** ở dưới (bố cục giống Buzz). Route cũ `/teams` redirect về đây.

**Phần Agents**
- `PageHeader`: “Agents” / “Ngoài 4 agent mặc định, bạn có thể tạo thêm agent nối với Claude Code hoặc Codex, rồi gom vào AI Team.” / nút **Tạo Agent**.
- Grid 2 cột (`gap-3.5`) card: `Logo @handle — display_name`, `RuntimeBadge`, mô tả, `Model: ... · quyền`, `Team: …` hoặc “Chưa thuộc team”, nhãn `Mặc định` nếu built-in; **nút bút chì (Sửa) trên mọi card** (kể cả built-in), nút thùng rác (Xoá) ẩn với built-in; trong lúc khởi động lại hiện badge vàng nhấp nháy **“↻ Đang khởi động lại…”**.
- **AgentForm** (dạng `Sheet`/modal, **dùng chung cho tạo và sửa**):
  0. **Logo** (`LogoPicker`, mục 2.2b).
  1. Tên Agent (Handle) — prefix `@`, tự lowercase, validate regex realtime. **Khi sửa: khoá, không đổi được.**
  2. Vai trò (display_name) + Nhóm quyền (role_key / permission preset: Chỉ đọc, Đọc/Ghi không commit, Đọc + chạy test, Tuỳ chỉnh; built-in giữ preset riêng).
  3. Loại Agent: `Claude Code (claude-agent-acp)` | `OpenAI Codex (codex-acp)` | **`OpenAI Custom (OpenAI-compatible, URL tuỳ chỉnh)`**.
  4. Model: với Claude Code/Codex — danh sách lọc theo runtime từ `/agents/models-catalog`; giá trị hiện tại luôn có trong danh sách.
  4b. **Khi chọn “OpenAI Custom”** — ô Model chuyển sang **nhập tự do** (combobox gợi ý `gpt-5`, `gpt-5-mini`, `gpt-4.1` + danh sách lấy từ `test-connection-draft`) và hiện khối nền xanh dương nhạt:
     - Ghi chú: “Agent gọi OpenAI Custom qua endpoint tương thích OpenAI (`/chat/completions`) với URL tuỳ chỉnh (OpenAI, Azure, OpenRouter, LiteLLM, Ollama, vLLM…). Agent loại này **chỉ trả lời văn bản**: không tự đọc/sửa file hay chạy lệnh trong workspace — hợp với vai trò BA, review, tóm tắt, giải thích.”
     - **Base URL** (mono, placeholder `https://api.openai.com/v1`, bỏ `/` cuối; sai định dạng → lỗi “Base URL không hợp lệ (cần http:// hoặc https://)”).
     - **API Key** (`type=password`, `autocomplete=off`; khi sửa agent đã có key: placeholder `•••••••• (để trống = giữ nguyên)`; bắt buộc khi tạo; dòng chú thích “API key được lưu mã hoá phía máy chủ và không bao giờ hiển thị lại”).
     - **Model** (bắt buộc).
     - Nút **Kiểm tra kết nối** (`POST /agents/test-connection-draft`): hiển thị “✔ Kết nối được <host> · GET /models 200 · 128 ms” hoặc “✘ <lý do>”.
     - **Nhóm quyền**: các lựa chọn ghi/chạy lệnh (*Đọc/Ghi không commit*, *Đọc + chạy test*) bị vô hiệu hoá (disabled) và tự chuyển về *Chỉ đọc*; thử lưu với nhóm quyền ghi → toast “Agent API không sửa file/chạy lệnh — chọn nhóm quyền Chỉ đọc hoặc Tuỳ chỉnh”.
  5. Mô tả chi tiết vai trò (System Prompt).
  6. AI Team (checkbox, tuỳ chọn) — chọn/bỏ để thêm/gỡ agent khỏi team. Bỏ agent khỏi team mà nó là agent duy nhất của team → toast “Không bỏ được: @x là agent duy nhất của team “…””.
  7. (Accordion “Nâng cao”) TagInput lệnh cấm/cho phép, Switch quyền chi tiết, màu, nút **Kiểm tra kết nối CLI** (`test-connection`).
  8. Nút **Huỷ** / **Lưu Agent** (tạo) hoặc **Lưu & khởi động lại** (sửa).
- **Quy tắc “sửa agent ⇒ khởi động lại agent”**:
  - Khi mở form sửa hiện dải cảnh báo vàng: “↻ Lưu thay đổi sẽ khởi động lại agent. Tiến trình ACP hiện tại bị đóng và một session mới được tạo với cấu hình mới.” + nếu có ticket đang `RUNNING`/`WAITING_*` dùng agent này: “Hiện có **N ticket** đang dùng @handle; lượt đang chạy sẽ bị dừng và chạy lại từ đầu bước đó.” (lấy từ `GET /agents/{id}/usage`).
  - Lưu có thay đổi cấu hình agent (logo, vai trò, runtime, **Base URL / API key / model**, quyền, prompt…) → `PATCH /agents/{id}` trả `restart: true` → UI hiện badge “Đang khởi động lại…” cho tới khi nhận event `agent_restarted` (WS) rồi toast “✔ @handle đã khởi động lại (runtime · model)”.
  - Lưu **không đổi gì** → không restart, toast “Không có thay đổi cấu hình agent, không cần khởi động lại”.
  - Chỉ đổi **thành viên AI Team** của agent → không restart (không đổi cấu hình agent).

**Phần Agent teams** (cùng trang)
- `PageHeader`: “Agent teams” / “Mỗi AI Team gồm **một hoặc nhiều** AI Agent. Thêm AI Team vào project để dùng các agent trong workflow.” / nút **Tạo AI Team**.
- Card team: `Logo` + tên + mô tả, chip các agent (`Logo @handle`), chân card “N agent · dùng trong M project”, nút **Sửa**.
- **TeamForm** (tạo + sửa, dùng chung): `LogoPicker`, tên, mô tả, chọn agent (checkbox lưới 2 cột; có thể nâng cấp multi-select có search + kéo thả sắp thứ tự `@dnd-kit/sortable`).
- **Bắt buộc ≥ 1 agent**: nút Lưu disable + dòng đỏ “AI Team phải có ít nhất 1 agent.” khi chưa chọn agent nào. Sửa team **không** khởi động lại agent nào.

### 4.3. Tạo project & `/projects/[id]/settings`
- **Hộp thoại “Tạo Project” chỉ có 3 trường** (không có thanh bước, không chọn AI Team):
  1. Tên project (bắt buộc), 2. **Đường dẫn thư mục local (ACP Working Directory)** (bắt buộc), 3. Nhánh Git để @leader push (mặc định `develop`).
  Nút: **Huỷ** / **Tạo project**.
- Khi rời ô đường dẫn → `POST /projects/validate-workspace` → dòng kết quả: ✔ Thư mục tồn tại, ✔ Git repo, ⚠ N file đang thay đổi, ✘ ngoài thư mục cho phép (chặn).
- Tạo xong: `POST /projects` (body **không** có member/team) → project trống → `router.push('/projects/{id}')`, sidebar thêm project lên đầu danh sách và mở rộng. **Không** tự mở bước tạo workflow, không tự gắn AI Team nào.
- Mô tả, Git remote, … chỉnh ở `/projects/[id]/settings`. Lối tắt “Dùng nhanh workflow Fix Bug mẫu” (`seed-default`: thêm *Core Bugfix Squad* + tạo/xuất bản workflow *Fix Bug*) nằm ở **trang tổng quan** khi project còn trống, không nằm trong hộp thoại tạo project.

### 4.4. `/projects/[id]/members` — “Thành viên & AI Team”
Mở từ nút **Thành viên & AI Team** ở tổng quan (modal trong mockup, trang `/members` trong bản đầy đủ). Đây là nơi **thêm AI Team / agent lẻ sau khi tạo project**.
- Người dùng: bảng (avatar, tên, email, project_role Select: MAINTAINER/REPORTER/VIEWER), nút thêm.
- **AI Teams**: danh sách mọi team (checkbox) với danh sách `@agent` con; tick/bỏ để thêm/gỡ khỏi project.
- **Agent lẻ**: checkbox từng agent chưa thuộc team đã thêm.
- Khối “Agent hiệu lực trong project” (effective agents).
- Gỡ agent/team đang được dùng trong graph của workflow chưa archived → 409 → toast liệt kê workflow cần sửa trước.

### 4.5. `/projects/[id]` — Tổng quan project
Mở khi **click tên project ở sidebar** (không phải khi click chevron).
- Header: icon, tên project, workspace path (mono) + nhánh, nút **Thành viên & AI Team** và nút chính **Tạo workflow**.
- **Dải tiến trình 4 bước** “✓ Project › 2 Workflow (xuất bản) › 3 Ticket › 4 Cửa sổ chat”: bước hiện tại được tô; giải thích thứ tự tạo.
- Khối **AI Team & Agent trong project**: chip team (tên + `@agent`), chip agent lẻ; nếu effective agents rỗng → dòng đỏ “Chưa có agent nào — hãy thêm AI Team trước khi tạo workflow.”
- Khối **Workflows (N)**: nếu 0 → `EmptyState` “Project chưa có workflow. Tạo workflow để bắt đầu nhận ticket. Ticket luôn được tạo bên trong một workflow.” + nút **Tạo workflow đầu tiên**. Nếu có: grid card **Workflow** (icon, tên, prefix, trạng thái Nháp / Đã xuất bản vN / Lưu trữ, mini pipeline `@ba → @developer → @tester → ✋ → @leader`, số ticket theo trạng thái, nút **Tạo ticket** (chỉ khi PUBLISHED), **Sửa luồng**, menu ⋯).
- Khối “Ticket gần đây” của toàn project (cột workflow để phân biệt).
- **Không còn tab “Tổng quan & Workflows”** riêng ở sidebar — tổng quan chỉ vào bằng tên project.

### 4.6. `/projects/[id]/workflows/[wid]` — Tổng quan workflow & tạo ticket
- Header: tên workflow, prefix, version đang xuất bản, nút **Sửa luồng** (→ `edit`), nút chính **+ Tạo ticket**.
- Bảng ticket của workflow: `#BUG-104`, tiêu đề, trạng thái, agent đang chạy, cập nhật lúc; filter trạng thái; click → cửa sổ chat.
- `CreateTicketDialog` (dùng chung cho nút ở sidebar và trang này):
  - Hiển thị cố định “Workflow: Fix Bug (BUG) · v3” (không đổi được trong dialog).
  - Tiêu đề (bắt buộc), Mô tả lỗi/yêu cầu (textarea; có thể **đính kèm file/ảnh** — dùng chung cơ chế attachment ở Phase 6 §5.7b).
  - Nút **Tạo & mở chat** → `POST /workflows/{wid}/tickets {auto_start: true}` → `router.push(chat_url)` (cửa sổ chat Phase 6). Tuỳ chọn phụ “Chỉ tạo, chưa chạy” (`auto_start: false`).

### 4.7. `/notifications` — Thông báo (thay cho “Hộp thư”)
Lưu **các sự kiện quan trọng cần người dùng tương tác**; không phải danh sách mọi ticket. Mỗi thông báo gắn với một ticket và được tạo tự động bởi engine (Phase 3 §6.2–6.3).
- `PageHeader`: “Thông báo” / “Các việc cần bạn tương tác: xác nhận kết quả, trả lời câu hỏi của agent. Thông báo được lưu lại sau khi xử lý.” / nút **Đánh dấu đã đọc**.
- Hai tab có số đếm: **Cần xử lý** (chưa `resolved_at`) | **Đã xử lý** (đã resolved, giữ làm lịch sử).
- Loại thông báo (icon + nhãn màu): **Cần xác nhận** (`CONFIRM`, vàng) — ticket chờ duyệt trước khi `@leader` commit & push; **Cần trả lời** (`INPUT`, xanh dương) — agent (VD `@ba`) hỏi thêm thông tin.
- Mỗi hàng: icon loại, tiêu đề đậm + chấm vàng nếu chưa đọc, mô tả, đường dẫn `Project / Workflow / #BUG-104 · tiêu đề ticket`, thời gian tương đối (“25 phút trước”), cột phải: nhãn loại (tab Cần xử lý) hoặc “✓ Đã xác nhận / Đã từ chối, gửi lại @developer / Đã trả lời” (tab Đã xử lý). Click → mở cửa sổ chat của ticket và đánh dấu đã đọc.
- Tự chuyển sang “Đã xử lý” khi người dùng confirm/reject/reply (hoặc ticket bị huỷ) — **do backend resolve**, UI chỉ nhận event `notification_resolved`.
- Badge ở sidebar = số thông báo chưa xử lý (ẩn khi 0). Trạng thái rỗng: “Không có gì cần xử lý 🎉”.

## 5. Data layer
- `src/lib/api/` sinh types bằng `openapi-typescript` từ `http://localhost:8000/openapi.json` (script `npm run gen:api`).
- TanStack Query: query keys trong `query-keys.ts`; invalidate sau mutation; toast (sonner) cho thành công/lỗi (hiển thị `detail` tiếng Việt từ backend).
- Auth: lưu JWT trong cookie httpOnly qua route handler `app/api/auth/*` của Next (proxy login) hoặc `localStorage` cho bản nội bộ — chọn cookie; `middleware.ts` redirect `/login` khi chưa đăng nhập.

## 6. Test
- Vitest + Testing Library: `AgentForm` (đổi runtime → danh sách model đổi; **chọn OpenAI Custom → hiện Base URL/API key/Model, ẩn select model ACP, vô hiệu nhóm quyền ghi; thiếu API key khi tạo → chặn; sửa không nhập key → giữ key; Kiểm tra kết nối hiện kết quả**; handle sai → lỗi; **sửa agent: handle bị khoá, hiện cảnh báo khởi động lại, lưu không đổi gì → không gọi restart**; `LogoPicker` chọn emoji / upload > 300KB bị từ chối), `Sidebar` (**click tên project không đổi thứ tự; mở project B không collapse project A; chevron đóng/mở; project ngoài top 5 được ghim ô thứ 5; “Xem tất cả” khi > 5**), `NotificationsPage` (tab, badge, chuyển sang Đã xử lý khi nhận `notification_resolved`).
- Playwright (`e2e/management.spec.ts`): login → trang **Agents & Teams**: tạo agent `@security_checker` (codex, chọn logo) → **sửa agent → thấy “Đang khởi động lại…” rồi hoàn tất** → tạo AI Team chứa nó (thử lưu team rỗng → bị chặn) → tạo project (chỉ 3 ô; mock validate-workspace) → **vào tổng quan project trống, KHÔNG có hộp thoại workflow tự bật** → “Thành viên & AI Team” thêm *Core Bugfix Squad* → “Tạo workflow” dùng mẫu Fix Bug, xuất bản → tạo ticket từ nút `+` ở sidebar → **URL chuyển sang trang chat của ticket** → sidebar hiển thị cây project → workflow → ticket; tạo 6 project → chỉ thấy 5 + “Xem tất cả”.

## 7. Definition of Done
- [ ] Giao diện khớp mockup về bố cục, màu, cỡ chữ (so sánh screenshot cạnh `aiTeams_gui.html`).
- [ ] CRUD Agent/Team/Project/Member chạy với backend thật.
- [ ] Không thể xoá agent built-in từ UI; nút ẩn.
- [ ] Không có đường nào trên UI tạo ticket khi project chưa có workflow đã xuất bản.
- [ ] Tạo project luôn cho ra **project trống**; AI Team, workflow, ticket tạo sau theo từng bước riêng.
- [ ] Sidebar: thứ tự project ổn định, mỗi project có nút thu gọn riêng, không còn ô tìm kiếm, “Hộp thư”, tab Tổng quan hay mục Agent trong project.
- [ ] Sửa agent luôn khởi động lại agent (có cảnh báo trước và trạng thái “Đang khởi động lại…”).
- [ ] Responsive tối thiểu: ≥ 1280px đầy đủ; < 1024px sidebar thu thành drawer.
- [ ] `npm run lint`, `npm run test`, `npx playwright test` pass.
